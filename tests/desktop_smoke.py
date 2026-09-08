"""Opt-in real Tk smoke test: run with Python on a desktop, not headless pytest CI."""

import json
import socket
import tempfile
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import psutil

from solora.desktop.window import ControlWindow
from solora.runtime.controller import ServerController
from solora.runtime.network import bind_socket
from solora.runtime.paths import RuntimePaths
from solora.runtime.settings import ConfigStore, RuntimeConfig


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def main() -> None:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="solora-tk-smoke-") as directory:
        paths = RuntimePaths.discover(Path(directory))
        paths.prepare()
        initial = RuntimeConfig(port=free_port())
        ConfigStore(paths.config).save(initial)
        controller = ServerController(paths)
        root = tk.Tk()
        window = ControlWindow(root, controller)
        stage = 0
        error: Exception | None = None
        report: dict[str, object] = {"tk": root.tk.call("info", "patchlevel")}
        occupied = bind_socket(RuntimeConfig(port=free_port()))
        conflict_port = occupied.getsockname()[1]
        changed_port = free_port()

        def tick() -> None:
            nonlocal stage, error
            try:
                if time.monotonic() - started > 60:
                    raise TimeoutError(f"Desktop smoke timed out at stage {stage}")
                if window.pending is not None:
                    root.after(100, tick)
                    return
                if stage == 0:
                    assert controller.status.state == "running", controller.status.error
                    assert controller.process is not None
                    report["startup_seconds"] = round(time.monotonic() - started, 2)
                    report["desktop_rss_mib"] = round(psutil.Process().memory_info().rss / 2**20, 1)
                    report["server_rss_mib"] = round(
                        psutil.Process(controller.process.pid).memory_info().rss / 2**20, 1
                    )
                    window.hide()
                elif stage == 1:
                    assert root.state() == "iconic", root.state()
                    report["hide"] = "native minimized window"
                    window.restore()
                elif stage == 2:
                    assert root.state() == "normal"
                    assert window.interface.tk_focusNext() is not window.interface
                    report["restore"] = "normal"
                    report["keyboard_focus_chain"] = "next focusable widget available"
                    with patch("solora.desktop.window.messagebox.showerror") as dialog:
                        window.port.set("0")
                        window.apply()
                        dialog.assert_called_once()
                    assert controller.store.load() == initial
                    window.port.set(str(changed_port))
                    window.apply()
                elif stage == 3:
                    assert controller.status.state == "running"
                    assert controller.store.load().port == changed_port
                    report["port_change"] = "passed"
                    window.port.set(str(conflict_port))
                    window.apply()
                elif stage == 4:
                    assert controller.status.state == "running"
                    assert "Previous settings restored" in controller.status.error
                    assert controller.store.load().port == changed_port
                    report["occupied_port_recovery"] = "passed"
                    window.restart()
                elif stage == 5:
                    assert controller.status.state == "running"
                    # No browser is required for this automated smoke. Native browser
                    # activation and screen-reader validation remain interactive gates.
                    with patch("webbrowser.open", return_value=True) as browser:
                        window.open_browser()
                        browser.assert_called_once_with(f"http://127.0.0.1:{changed_port}/")
                    report["browser_target"] = "healthy current URL (launch mocked)"
                    window.stop()
                elif stage == 6:
                    assert controller.status.state == "stopped"
                    window.restart()
                elif stage == 7:
                    assert controller.status.state == "running"
                    report["stop_restart"] = "passed"
                    window.quit()
                    return
                stage += 1
                root.after(250, tick)
            except Exception as failure:
                error = failure
                root.destroy()

        root.after(100, tick)
        try:
            root.mainloop()
        finally:
            controller.close()
            window.worker.shutdown(wait=True)
            occupied.close()
        if error is not None:
            raise error
        report["quit"] = "child stopped, owner released"
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
