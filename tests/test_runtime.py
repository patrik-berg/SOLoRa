"""Hardware-free production runtime, readiness, and real child-process regression tests."""

import io
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
from unittest.mock import MagicMock
from urllib.request import ProxyHandler, build_opener

import pytest
from alembic import command
from fastapi.testclient import TestClient
from filelock import Timeout
from packaging.version import Version
from sqlalchemy import text

from solora.adapters.persistence.database import Database
from solora.app import create_app
from solora.domain.protocol import PROTOCOL_VERSION
from solora.runtime.cli import main
from solora.runtime.controller import ServerController, launch_command
from solora.runtime.health import assets_available, migration_config, readiness
from solora.runtime.network import bind_socket, interfaces
from solora.runtime.ownership import owner_lock
from solora.runtime.paths import RuntimePaths
from solora.runtime.server import emit, serve
from solora.runtime.settings import ConfigStore, RuntimeConfig
from solora.version import APP_VERSION


@pytest.fixture
def runtime(tmp_path: Path) -> RuntimePaths:
    paths = RuntimePaths.discover(tmp_path / "profile")
    # Keep real migrations, supply tiny but structurally valid production assets.
    application = tmp_path / "application"
    frontend = application / "frontend" / "dist"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text('<script src="/main.js"></script>', encoding="utf-8")
    (frontend / "main.js").write_text('document.title="SOLoRa"', encoding="utf-8")
    import shutil

    shutil.copytree(paths.migrations, application / "backend" / "migrations")
    paths = replace(paths, application=application)
    paths.prepare()
    ConfigStore(paths.config).save(RuntimeConfig(port=free_port()))
    return paths


def free_port(bind: str = "127.0.0.1") -> int:
    with socket.socket() as listener:
        listener.bind((bind, 0))
        return int(listener.getsockname()[1])


def http_json(url: str) -> dict[str, object]:
    with build_opener(ProxyHandler({})).open(url, timeout=3) as response:
        result: dict[str, object] = json.load(response)
        return result


def test_runtime_paths_outside_application_and_platform_conventions(
    runtime: RuntimePaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert runtime.application not in runtime.data.parents
    assert len({runtime.data, runtime.config, runtime.logs, runtime.runtime}) == 4
    assert "solora.db" in runtime.database_url
    with pytest.raises(ValueError, match="outside"):
        replace(runtime, data=runtime.application / "data").prepare()
    defaults = RuntimePaths.discover()
    assert defaults.data.name == "data"
    assert defaults.config.name == "config"
    monkeypatch.setattr(sys, "_MEIPASS", str(runtime.application), raising=False)
    assert RuntimePaths.discover().application == runtime.application


@pytest.mark.parametrize("port", [0, -1, 65536, True, 1.5, "8000"])
def test_invalid_port_rejected(port: int) -> None:
    with pytest.raises(ValueError, match="Port"):
        RuntimeConfig(port=port)


@pytest.mark.parametrize("bind", ["localhost", "::1", "not an ip", "224.0.0.1", "255.255.255.255"])
def test_invalid_bind_rejected(bind: str) -> None:
    with pytest.raises(ValueError):
        RuntimeConfig(bind=bind)


def test_config_persistence_validation_and_urls(runtime: RuntimePaths) -> None:
    store = ConfigStore(runtime.config)
    config = RuntimeConfig(bind="0.0.0.0", port=9123, lan_confirmed=True, start_minimized=True)
    store.save(config)
    assert ConfigStore(runtime.config).load() == config
    assert config.urls(("192.168.1.2", "192.168.1.2")) == (
        "http://127.0.0.1:9123/",
        "http://192.168.1.2:9123/",
    )
    with pytest.raises(ValueError, match="Confirm LAN"):
        RuntimeConfig(bind="192.168.1.2")
    with pytest.raises(ValueError, match="booleans"):
        RuntimeConfig(start_minimized=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="mode"):
        RuntimeConfig(mode="invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="schema"):
        RuntimeConfig(schema_version=2)
    for invalid in ("[]", "{} invalid", '{"port": false}', '{"unknown": 1}'):
        store.path.write_text(invalid, encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid bootstrap"):
            store.load()
        assert store.path.read_text() == invalid
    store.path.unlink()
    assert store.load() == RuntimeConfig()


def test_atomic_save_failure_preserves_config(
    runtime: RuntimePaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ConfigStore(runtime.config)
    original = store.load()

    def fail(*args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        store.save(replace(original, port=12345))
    assert store.load() == original
    assert list(runtime.config.glob(".runtime-*")) == []


def test_listener_conflict_and_interface_discovery(
    runtime: RuntimePaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = ConfigStore(runtime.config).load()
    with bind_socket(config), pytest.raises(OSError, match="occupied port"):
        bind_socket(config)
    with bind_socket(config):
        pass
    import psutil

    monkeypatch.setattr(
        psutil,
        "net_if_addrs",
        lambda: {
            "Wi-Fi": [
                MagicMock(family=socket.AF_INET, address="192.168.1.42"),
                MagicMock(family=socket.AF_INET6, address="::1"),
            ],
        },
    )
    assert interfaces()["Wi-Fi — 192.168.1.42"] == "192.168.1.42"


def test_readiness_assets_schema_state_and_versions(runtime: RuntimePaths) -> None:
    database = Database(runtime.database_url)
    try:
        assert readiness(database, runtime.frontend, runtime.migrations)["status"] == "unhealthy"
        command.upgrade(migration_config(runtime.migrations, runtime.database_url), "head")
        with TestClient(
            create_app(
                database_url=runtime.database_url,
                frontend_path=runtime.frontend,
                runtime_paths=runtime,
                runtime_config=ConfigStore(runtime.config).load(),
            )
        ) as client:
            healthy = client.get("/health/ready")
            assert healthy.status_code == 200
            assert all(healthy.json()["checks"].values())
            assert healthy.json()["app_version"] == APP_VERSION
            assert healthy.json()["protocol_version"] == PROTOCOL_VERSION == 1
            assert Version(version("solora")) == Version(APP_VERSION)
            assert client.get("/api/settings/meshtastic").json()["connected"] is False
            assert client.get("/").status_code == 200
            assert client.get("/main.js").status_code == 200
            settings = client.get("/api/settings/runtime").json()
            assert settings["active"]["port"] == ConfigStore(runtime.config).load().port
            desired = replace(ConfigStore(runtime.config).load(), port=9124)
            ConfigStore(runtime.config).save(desired)
            assert client.get("/api/settings/runtime").json()["configured"]["port"] == 9124
            (runtime.frontend / "main.js").unlink()
            assert client.get("/health/ready").status_code == 503
        with database.engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='old'"))
        assert readiness(database, runtime.frontend, runtime.migrations)["status"] == "unhealthy"
    finally:
        database.close()


@pytest.mark.parametrize(
    "markup",
    [
        "<h1>empty</h1>",
        '<script src="https://remote/a.js"></script>',
        '<script src="/../outside.js"></script>',
        '<link rel="stylesheet">',
        '<link rel="modulepreload" href="/missing.js">',
    ],
)
def test_incomplete_production_assets_fail(runtime: RuntimePaths, markup: str) -> None:
    (runtime.frontend / "index.html").write_text(markup, encoding="utf-8")
    assert not assets_available(runtime.frontend)
    assert not assets_available(runtime.frontend / "missing")


def test_runtime_migrations_ignore_development_database_environment(
    runtime: RuntimePaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = runtime.data / "wrong.db"
    monkeypatch.setenv("SOLORA_DATABASE_URL", f"sqlite:///{other}")
    command.upgrade(migration_config(runtime.migrations, runtime.database_url), "head")
    assert not other.exists()
    assert (runtime.data / "solora.db").exists()


def test_real_child_lifecycle_restart_existing_data_and_recovery(runtime: RuntimePaths) -> None:
    controller = ServerController(runtime)
    try:
        initial = ConfigStore(runtime.config).load()
        assert controller.start().state == "running"
        assert controller.start().state == "running"
        assert http_json(initial.urls()[0] + "health/ready")["status"] == "healthy"
        database = Database(runtime.database_url)
        with database.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO threads(title, sync_id) VALUES ('Retained', randomblob(12))")
            )
        database.close()
        with pytest.raises(Timeout):
            ServerController(runtime)
        assert main(["--profile", str(runtime.data.parent), "configure", "--port", "9020"]) == 1
        assert controller.restart().state == "running"
        with bind_socket(RuntimeConfig(port=free_port())) as occupied:
            port = int(occupied.getsockname()[1])
            failed = controller.apply(replace(initial, port=port))
            assert failed.state == "running"
            assert "Previous settings restored" in failed.error
            assert ConfigStore(runtime.config).load() == initial
            controller.events.put({"state": "running"})
            assert "Previous settings restored" in controller.refresh().error
        next_config = replace(
            initial, port=free_port("0.0.0.0"), bind="0.0.0.0", lan_confirmed=True
        )
        applied = controller.apply(next_config)
        assert applied.state == "running", applied.error
        assert not applied.error
        assert controller.active_config == next_config
        assert http_json(next_config.urls()[0] + "health/ready")["status"] == "healthy"
        assert controller.stop().state == "stopped"
        assert controller.process is None
        with pytest.raises(ValueError, match="not healthy"):
            controller.open_browser()
        database = Database(runtime.database_url)
        with database.engine.connect() as connection:
            assert connection.execute(text("SELECT title FROM threads")).scalar() == "Retained"
        database.close()
    finally:
        controller.close()
    with owner_lock(runtime.data, "server"), owner_lock(runtime.data, "desktop"):
        pass


def test_failed_start_can_be_repaired_without_http(runtime: RuntimePaths) -> None:
    controller = ServerController(runtime)
    try:
        with bind_socket(ConfigStore(runtime.config).load()):
            assert controller.start().state == "error"
            assert "Cannot listen" in controller.status.error
            assert controller.apply(RuntimeConfig(port=free_port())).state == "running"
        controller.stop()
        (runtime.frontend / "main.js").unlink()
        assert controller.start().state == "error"
        assert "assets missing" in controller.status.error
        controller.stop()
        controller.store.path.write_text("invalid", encoding="utf-8")
        assert controller.start().state == "error"
        (runtime.frontend / "main.js").write_text("/* restored */", encoding="utf-8")
        assert controller.apply(RuntimeConfig(port=free_port())).state == "running"
    finally:
        controller.close()


def test_parent_pipe_eof_cleans_child_and_headless_has_no_gui(runtime: RuntimePaths) -> None:
    # Intercept GUI/browser imports, then run real headless core with no Node tools in PATH.
    code = """
import sys
class NoDesktop:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'solora.app':
            raise RuntimeError('Development singleton in production')
        if fullname.startswith(('tkinter', '_tkinter', 'solora.desktop', 'webbrowser')):
            raise RuntimeError('GUI dependency in headless: ' + fullname)
sys.meta_path.insert(0, NoDesktop())
from solora.runtime.cli import main
raise SystemExit(main(sys.argv[1:]))
"""
    args = launch_command(runtime)[3:]
    environment = dict(os.environ, PATH="")
    process = subprocess.Popen(
        [sys.executable, "-c", code, *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        assert process.stdout is not None
        event = json.loads(process.stdout.readline())
        assert event["state"] == "running"
        assert process.stdin is not None
        process.stdin.close()
        assert process.wait(timeout=12) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()


def test_cli_offline_config_and_owner_protection(
    runtime: RuntimePaths, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["--profile", str(runtime.data.parent)]
    store = ConfigStore(runtime.config)
    store.save(replace(store.load(), start_minimized=True))
    assert main([*args, "configure", "--port", "9321"]) == 0
    assert store.load().start_minimized is True
    assert main([*args, "status"]) == 0
    assert "9321" in capsys.readouterr().out
    assert main([*args, "configure", "--port", "0"]) == 1
    store.path.write_text("invalid", encoding="utf-8")
    assert main([*args, "configure", "--port", "9321"]) == 0
    with owner_lock(runtime.data, "desktop"):
        assert serve(runtime) == 1
    with owner_lock(runtime.data, "server"):
        assert serve(runtime) == 1
    emit({"state": "stopped"}, None)
    output = io.StringIO()
    emit({"state": "stopped"}, output)
    assert json.loads(output.getvalue())["state"] == "stopped"


def test_controller_spawn_failure_and_readiness_timeout(
    runtime: RuntimePaths, monkeypatch: pytest.MonkeyPatch
) -> None:

    controller = ServerController(runtime, timeout=0)
    try:

        def fail(*args: object, **kwargs: object) -> None:
            raise OSError("cannot execute")

        with monkeypatch.context() as patch:
            patch.setattr(subprocess, "Popen", fail)
            assert controller.start().error == "cannot execute"
        assert "timed out" in controller.start().error
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        assert launch_command(runtime)[1] == "--application"
    finally:
        controller.close()


def test_abrupt_desktop_death_releases_owned_server(runtime: RuntimePaths) -> None:
    import psutil

    code = """
import json, sys, time
from pathlib import Path
from dataclasses import replace
from solora.runtime.paths import RuntimePaths
from solora.runtime.controller import ServerController
paths = replace(RuntimePaths.discover(Path(sys.argv[1])), application=Path(sys.argv[2]))
owner = ServerController(paths)
assert owner.start().state == 'running'
print(owner.process.pid, flush=True)
time.sleep(60)
"""
    parent = subprocess.Popen(
        [sys.executable, "-c", code, str(runtime.data.parent), str(runtime.application)],
        stdout=subprocess.PIPE,
        text=True,
    )
    child: psutil.Process | None = None
    try:
        assert parent.stdout is not None
        child = psutil.Process(int(parent.stdout.readline()))
        parent.kill()
        parent.wait(timeout=5)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try:
                with owner_lock(runtime.data, "server"), owner_lock(runtime.data, "desktop"):
                    break
            except Timeout:
                time.sleep(0.1)
        else:
            pytest.fail("Orphan server kept the data profile locked after parent death")
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()
        if child is not None and child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
            child.terminate()
        if parent.stdout:
            parent.stdout.close()


def test_controller_rejects_stale_local_health(tmp_path: Path) -> None:
    from solora.runtime.controller import ServerStatus

    controller = ServerController(RuntimePaths.discover(tmp_path))
    try:
        controller.status = ServerStatus("running")
        controller.last_event = time.monotonic() - 11
        assert "stale" in controller.refresh().error
    finally:
        controller.close()
