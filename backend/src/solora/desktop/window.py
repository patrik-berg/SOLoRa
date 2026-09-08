"""Thin ttk proof-of-concept. Lifecycle work never blocks Tk's event thread."""

import tkinter as tk
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from tkinter import messagebox, ttk

from filelock import Timeout

from solora.runtime.controller import ServerController, ServerStatus
from solora.runtime.network import interfaces
from solora.runtime.paths import RuntimePaths
from solora.runtime.settings import RuntimeConfig
from solora.version import APP_VERSION


class ControlWindow:
    def __init__(self, root: tk.Tk, controller: ServerController) -> None:
        self.root = root
        self.controller = controller
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.pending: Future[ServerStatus] | None = None
        self.quitting = False
        root.title("SOLoRa LINK")
        root.minsize(520, 500)
        root.protocol("WM_DELETE_WINDOW", self.hide)
        root.bind("<Control-q>", lambda _: self.quit())
        root.bind("<Command-q>", lambda _: self.quit())
        if root.tk.call("tk", "windowingsystem") == "aqua":
            root.createcommand("::tk::mac::ReopenApplication", self.restore)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=f"SOLoRa LINK   v{APP_VERSION}", font=("TkDefaultFont", 18)).grid(
            sticky="w"
        )
        self.identity = tk.StringVar(value="System identity will appear after startup")
        ttk.Label(frame, textvariable=self.identity).grid(sticky="w", pady=8)
        self.status = tk.StringVar(value="Starting…")
        ttk.Label(frame, textvariable=self.status, wraplength=480).grid(sticky="w", pady=8)
        self.radio = tk.StringVar(value="Meshtastic: Offline")
        ttk.Label(frame, textvariable=self.radio).grid(sticky="w")
        ttk.Label(frame, text="Available at (LAN reachability not verified):").grid(
            sticky="w", pady=(12, 0)
        )
        self.urls = tk.StringVar()
        ttk.Entry(frame, textvariable=self.urls, state="readonly").grid(sticky="ew", pady=4)
        self.networks = interfaces()
        ttk.Label(frame, text="Interface / explicit IPv4 address:").grid(sticky="w", pady=(12, 0))
        self.bind = tk.StringVar()
        self.interface = ttk.Combobox(frame, textvariable=self.bind, values=list(self.networks))
        self.interface.grid(sticky="ew")
        ttk.Label(frame, text="HTTP port:").grid(sticky="w", pady=(8, 0))
        self.port = tk.StringVar()
        ttk.Entry(frame, textvariable=self.port).grid(sticky="ew")
        self.minimized = tk.BooleanVar()
        ttk.Checkbutton(
            frame, text="Start minimized (after healthy startup)", variable=self.minimized
        ).grid(sticky="w", pady=8)
        ttk.Label(frame, text="Run at login: available with the packaged app in PR B.").grid(
            sticky="w"
        )
        actions = ttk.Frame(frame)
        actions.grid(sticky="ew", pady=12)
        self.buttons: list[ttk.Button] = []
        for label, callback in (
            ("Apply", self.apply),
            ("Restart", self.restart),
            ("Stop", self.stop),
        ):
            button = ttk.Button(actions, text=label, command=callback)
            button.pack(side="left")
            self.buttons.append(button)
        self.open_button = ttk.Button(actions, text="Open SOLoRa", command=self.open_browser)
        self.open_button.pack(side="left")
        footer = ttk.Frame(frame)
        footer.grid(sticky="ew")
        ttk.Button(footer, text="Hide", command=self.hide).pack(side="left")
        ttk.Button(footer, text="Quit", command=self.quit).pack(side="right")
        self.load_fields()
        self.initial_start = True
        self.submit(controller.start)
        root.after(100, self.tick)

    def load_fields(self) -> None:
        try:
            config = self.controller.store.load()
        except ValueError as error:
            config = RuntimeConfig()
            self.status.set(str(error))
        self.bind.set(
            next(
                (name for name, address in self.networks.items() if address == config.bind),
                config.bind,
            )
        )
        self.port.set(str(config.port))
        self.minimized.set(config.start_minimized)

    def submit(self, action: Callable[[], ServerStatus]) -> None:
        if self.pending is None:
            self.status.set("Working…")
            for button in self.buttons:
                button.state(["disabled"])
            self.open_button.state(["disabled"])
            self.pending = self.worker.submit(action)

    def apply(self) -> None:
        try:
            bind = self.networks.get(self.bind.get(), self.bind.get().strip())
            lan = not bind.startswith("127.")
            if lan and not messagebox.askyesno(
                "LAN access",
                "This forum has no authentication. Allow LAN access and restart?",
                parent=self.root,
            ):
                return
            desired = RuntimeConfig(
                bind=bind,
                port=int(self.port.get()),
                start_minimized=self.minimized.get(),
                lan_confirmed=lan,
            )
            self.submit(lambda: self.controller.apply(desired))
        except ValueError as error:
            messagebox.showerror("Invalid settings", str(error), parent=self.root)

    def restart(self) -> None:
        self.submit(self.controller.restart)

    def stop(self) -> None:
        self.submit(self.controller.stop)

    def open_browser(self) -> None:
        try:
            if not self.controller.open_browser():
                raise ValueError("Could not open the default browser; copy the address instead")
        except (OSError, ValueError) as error:
            messagebox.showerror("Open SOLoRa", str(error), parent=self.root)

    def hide(self) -> None:
        # Accessible native taskbar/Dock minimization, not an unreachable hidden window.
        self.root.iconify()

    def restore(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def quit(self) -> None:
        self.quitting = True
        if self.pending is None:
            self.submit(self.controller.stop)

    def tick(self) -> None:
        if self.pending is not None and self.pending.done():
            try:
                self.pending.result()
            except Exception as error:
                self.controller.status = ServerStatus("error", str(error))
            self.pending = None
            self.load_fields()
            for button in self.buttons:
                button.state(["!disabled"])
        if self.pending is None:
            if self.quitting:
                if self.controller.process is not None:
                    self.submit(self.controller.stop)
                    self.root.after(100, self.tick)
                    return
                self.controller.close()
                self.worker.shutdown(wait=False)
                self.root.destroy()
                return
            state = self.controller.refresh()
            self.status.set(f"{state.state.capitalize()} {state.error}")
            details = state.details
            stale = " (stale)" if state.state != "running" else ""
            role = {
                "CLIENT": "Client",
                "PRIMARY": "Primary server (experimental)",
                "BACKUP": "Backup server (experimental)",
            }.get(str(details.get("system_role")), "—")
            self.identity.set(f"{details.get('system_name', '—')} · {role}{stale}")
            self.radio.set(f"Meshtastic: {details.get('radio', 'Offline')}{stale}")
            if state.state == "running" and self.controller.active_config is not None:
                config = self.controller.active_config
                self.urls.set(
                    "  ".join(
                        config.urls(
                            tuple(
                                address
                                for address in self.networks.values()
                                if address not in ("0.0.0.0", "127.0.0.1")
                            )
                        )
                    )
                )
                self.open_button.state(["!disabled"])
                if self.initial_start and config.start_minimized:
                    self.hide()
                self.initial_start = False
            else:
                self.open_button.state(["disabled"])
                self.urls.set("Not ready")
        request = self.controller.paths.runtime / "restore.request"
        if request.exists():
            request.unlink(missing_ok=True)
            self.restore()
        self.root.after(100, self.tick)


def run(paths: RuntimePaths) -> int:
    try:
        controller = ServerController(paths)
    except Timeout:
        # Same-user UI-only signal, never a command that mutates configuration or service.
        (paths.runtime / "restore.request").touch(mode=0o600)
        return 0
    try:
        root = tk.Tk()
        ControlWindow(root, controller)
        root.mainloop()
    finally:
        controller.close()
    return 0
