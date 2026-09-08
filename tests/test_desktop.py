"""Widget-independent lifecycle tests plus a mocked ttk presentation contract."""

import importlib
import io
import queue
import subprocess
import sys
from concurrent.futures import Future
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from solora.runtime.controller import ServerController, ServerStatus
from solora.runtime.paths import RuntimePaths
from solora.runtime.settings import RuntimeConfig


class Value:
    def __init__(self, value: object = "") -> None:
        self.value = value

    def get(self) -> Any:
        return self.value

    def set(self, value: object) -> None:
        self.value = value


class ImmediateWorker:
    def submit(self, action: Any) -> Future[ServerStatus]:
        future: Future[ServerStatus] = Future()
        try:
            future.set_result(action())
        except Exception as error:
            future.set_exception(error)
        return future

    def shutdown(self, **kwargs: object) -> None:
        pass


@pytest.fixture
def presentation(monkeypatch: pytest.MonkeyPatch) -> Any:
    # Headless CI needs neither _tkinter nor a display to test presentation wiring.
    fake = ModuleType("tkinter")
    for name, value in {
        "StringVar": Value,
        "BooleanVar": Value,
        "Tk": MagicMock(),
        "ttk": MagicMock(),
        "messagebox": MagicMock(),
    }.items():
        setattr(fake, name, value)
    monkeypatch.setitem(sys.modules, "tkinter", fake)
    monkeypatch.delitem(sys.modules, "solora.desktop.window", raising=False)
    module = importlib.import_module("solora.desktop.window")
    monkeypatch.setattr(module, "ThreadPoolExecutor", lambda **_: ImmediateWorker())
    monkeypatch.setattr(
        module, "interfaces", lambda: {"Localhost": "127.0.0.1", "Wi-Fi": "192.168.1.42"}
    )
    yield module
    sys.modules.pop("solora.desktop.window", None)


def test_control_window_wires_recovery_status_hide_restore_and_quit(
    presentation: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = RuntimePaths.discover(tmp_path)
    controller = ServerController(paths)
    root = MagicMock()
    root.tk.call.return_value = "aqua"
    status = ServerStatus(
        "running",
        details={"system_name": "Base North", "system_role": "PRIMARY", "radio": "Offline"},
    )

    def start() -> ServerStatus:
        controller.status = status
        controller.active_config = controller.store.load()
        return status

    monkeypatch.setattr(controller, "start", start)
    controller.store.save(RuntimeConfig(start_minimized=True))
    window = presentation.ControlWindow(root, controller)
    try:
        window.tick()
        assert window.identity.get() == "Base North · Primary server (experimental)"
        assert window.urls.get() == "http://127.0.0.1:8000/"
        root.iconify.assert_called_once()
        root.createcommand.assert_called_once()
        window.hide()
        window.restore()
        root.deiconify.assert_called_once()
        window.port.set("wrong")
        window.apply()
        presentation.messagebox.showerror.assert_called_once()
        window.port.set("9010")
        window.bind.set("Wi-Fi")
        presentation.messagebox.askyesno.return_value = False
        window.apply()
        assert controller.store.load().port == 8000
        presentation.messagebox.askyesno.return_value = True
        window.apply()
        window.tick()
        assert controller.store.load().port == 9010
        assert controller.store.load().lan_confirmed is True
        (paths.runtime / "restore.request").touch()
        window.tick()
        assert not (paths.runtime / "restore.request").exists()
        import webbrowser

        browser = MagicMock(return_value=True)
        monkeypatch.setattr(webbrowser, "open", browser)
        window.open_browser()
        browser.assert_called_once_with("http://192.168.1.42:9010/")
        browser.return_value = False
        window.open_browser()
        assert presentation.messagebox.showerror.call_count == 2
        window.stop()
        window.tick()
        assert "stale" in window.identity.get()
        assert window.urls.get() == "Not ready"
        window.restart()
        window.tick()
        assert controller.status.state == "running"
        window.quit()
        window.tick()
        root.destroy.assert_called_once()
    finally:
        controller.close()


def test_control_window_handles_bad_config_and_worker_error(
    presentation: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = ServerController(RuntimePaths.discover(tmp_path))
    controller.store.path.write_text("corrupt", encoding="utf-8")
    root = MagicMock()

    def fail() -> ServerStatus:
        raise OSError("failed start")

    monkeypatch.setattr(controller, "start", fail)
    window = presentation.ControlWindow(root, controller)
    try:
        # Submitting while busy must not create another owner/operation.
        duplicate = MagicMock()
        window.submit(duplicate)
        duplicate.assert_not_called()
        window.tick()
        assert "failed start" in window.status.get()
        assert window.bind.get() == "Localhost"
        assert window.port.get() == "8000"
        window.quit()
        window.tick()
    finally:
        controller.close()


def test_second_desktop_launch_requests_restore_without_new_server(
    presentation: Any, tmp_path: Path
) -> None:
    paths = RuntimePaths.discover(tmp_path)
    controller = ServerController(paths)
    try:
        assert presentation.run(paths) == 0
        assert (paths.runtime / "restore.request").exists()
    finally:
        controller.close()


def test_window_run_always_cleans_owner(
    presentation: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = RuntimePaths.discover(tmp_path)
    controller = ServerController(paths)
    fake_window = MagicMock()
    monkeypatch.setattr(presentation, "ControlWindow", fake_window)
    monkeypatch.setattr(presentation, "ServerController", lambda _: controller)
    assert presentation.run(paths) == 0
    assert not controller.owner.is_locked


def test_owned_child_shutdown_escalation_and_event_filter(tmp_path: Path) -> None:
    controller = ServerController(RuntimePaths.discover(tmp_path))
    try:
        events: queue.Queue[dict[str, object]] = queue.Queue()
        controller._read_events(io.StringIO('noise\n[]\n{}\n{"state":"running"}\n'), events)
        assert events.get_nowait() == {"state": "running"}
        process = MagicMock()
        process.wait.side_effect = [
            subprocess.TimeoutExpired("owned", 8),
            subprocess.TimeoutExpired("owned", 2),
            0,
        ]
        controller.process = process
        controller.stop()
        process.stdin.close.assert_called_once()
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        assert controller.status.state == "stopped"
        process = MagicMock(returncode=9)
        process.poll.return_value = 9
        controller.process = process
        assert "exited (9)" in controller.refresh().error
    finally:
        controller.close()
