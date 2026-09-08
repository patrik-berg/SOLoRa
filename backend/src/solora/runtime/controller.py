"""Testable desktop process owner; no widgets and no dependency on HTTP control."""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field, replace
from typing import TextIO

from solora.runtime.ownership import owner_lock
from solora.runtime.paths import RuntimePaths
from solora.runtime.settings import ConfigStore, RuntimeConfig


def launch_command(paths: RuntimePaths) -> list[str]:
    executable = (
        [sys.executable]
        if getattr(sys, "frozen", False)
        else [sys.executable, "-m", "solora.runtime.cli"]
    )
    # Explicit paths also support future service adapters with non-user directory layouts.
    return [
        *executable,
        "--application",
        str(paths.application),
        "--data",
        str(paths.data),
        "--config",
        str(paths.config),
        "--logs",
        str(paths.logs),
        "--runtime",
        str(paths.runtime),
        "server",
        "--managed",
    ]


@dataclass
class ServerStatus:
    state: str = "stopped"
    error: str = ""
    details: dict[str, object] = field(default_factory=dict)


class ServerController:
    def __init__(self, paths: RuntimePaths, *, timeout: float = 30) -> None:
        paths.prepare()
        self.paths = paths
        self.store = ConfigStore(paths.config)
        self.owner = owner_lock(paths.data, "desktop")
        self.owner.acquire()
        self.process: subprocess.Popen[str] | None = None
        self.events: queue.Queue[dict[str, object]] = queue.Queue()
        self.status = ServerStatus()
        self.timeout = timeout
        self.active_config: RuntimeConfig | None = None
        self.last_event = time.monotonic()
        self.notice = ""

    def _read_events(self, stream: TextIO, events: queue.Queue[dict[str, object]]) -> None:
        with stream:
            for line in stream:
                try:
                    value = json.loads(line)
                    if isinstance(value, dict) and "state" in value:
                        events.put(value)
                except ValueError:
                    continue

    def refresh(self) -> ServerStatus:
        while not self.events.empty():
            value = self.events.get_nowait()
            self.last_event = time.monotonic()
            self.status = ServerStatus(
                str(value["state"]), str(value.get("error", "")) or self.notice, value
            )
        if self.process is not None and self.process.poll() is not None:
            self.status.state = "error"
            self.status.error = (
                self.status.error
                or f"Server exited ({self.process.returncode}); see server-startup.log"
            )
        elif self.status.state == "running" and time.monotonic() - self.last_event > 10:
            self.status = ServerStatus(
                "error", "Local readiness status is stale; restart the server", self.status.details
            )
        return self.status

    def start(self) -> ServerStatus:
        if self.process is not None and self.process.poll() is None:
            return self.refresh()
        if self.process is not None:
            self.stop()
        self.status = ServerStatus("starting")
        self.notice = ""
        try:
            configured = self.store.load()
            self.events = queue.Queue()
            environment = os.environ.copy()
            environment.pop("SOLORA_DATABASE_URL", None)
            log = self.paths.logs / "server-startup.log"
            # Startup diagnostics are bounded per launch; main service log is rotating.
            with log.open("w", encoding="utf-8") as stderr:
                self.process = subprocess.Popen(
                    launch_command(self.paths),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=stderr,
                    text=True,
                    encoding="utf-8",
                    env=environment,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            self.active_config = configured
            assert self.process.stdout is not None
            threading.Thread(
                target=self._read_events, args=(self.process.stdout, self.events), daemon=True
            ).start()
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                self.refresh()
                if self.status.state != "starting":
                    return self.status
                # Local lifecycle wait only. No radio retries or airtime policy changes.
                threading.Event().wait(0.05)
            self.stop()
            self.status = ServerStatus(
                "error", "Server readiness timed out; check server-startup.log"
            )
        except (OSError, ValueError) as error:
            self.status = ServerStatus("error", str(error))
        return self.status

    def stop(self) -> ServerStatus:
        process = self.process
        if process is not None:
            if process.stdin is not None:
                process.stdin.close()  # EOF requests graceful exit, including on parent crash.
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            self.process = None
        self.events = queue.Queue()
        self.active_config = None
        self.status = ServerStatus("stopped", details=self.status.details)
        return self.status

    def restart(self) -> ServerStatus:
        self.stop()
        return self.start()

    def apply(self, desired: RuntimeConfig) -> ServerStatus:
        try:
            previous = self.store.load()
        except ValueError:
            previous = None
        self.stop()
        self.store.save(replace(desired, mode="desktop"))
        result = self.start()
        if result.state == "error" and previous is not None:
            reason = result.error
            self.stop()
            self.store.save(previous)
            result = self.start()
            self.notice = f"New settings failed: {reason}. Previous settings restored."
            result.error = f"{self.notice} {result.error}"
        return result

    def open_browser(self) -> bool:
        if self.refresh().state != "running" or self.active_config is None:
            raise ValueError("SOLoRa is not healthy; start or repair the server first")
        import webbrowser

        return webbrowser.open(self.active_config.urls()[0])

    def close(self) -> None:
        try:
            self.stop()
        finally:
            self.owner.release()
