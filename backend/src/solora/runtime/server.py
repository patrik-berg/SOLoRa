"""Headless production entry: exclusive ownership, migrations, assets, HTTP."""

import asyncio
import json
import logging
import sys
import threading
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from typing import TextIO

import uvicorn
from alembic import command
from alembic.util.exc import CommandError
from filelock import Timeout

from solora.adapters.persistence.settings_repository import SqlAlchemyChannelSettingsRepository
from solora.adapters.persistence.system_settings_repository import (
    SqlAlchemySystemSettingsRepository,
)
from solora.application.system_settings import SystemSettingsService
from solora.runtime.health import assets_available, migration_config, readiness
from solora.runtime.network import bind_socket
from solora.runtime.ownership import owner_lock
from solora.runtime.paths import RuntimePaths
from solora.runtime.settings import ConfigStore
from solora.web.application import create_app


def emit(value: dict[str, object], output: TextIO | None) -> None:
    if output is not None:
        output.write(json.dumps(value) + "\n")
        output.flush()


def serve(paths: RuntimePaths, *, managed: bool = False) -> int:
    paths.prepare()
    output = sys.stdout
    stopped = threading.Event()
    if managed:

        def watch_parent() -> None:
            # Inherited stdin is private IPC: explicit stop OR parent death closes it.
            if sys.stdin is not None:
                sys.stdin.readline()
            stopped.set()

        threading.Thread(target=watch_parent, daemon=True).start()
    try:
        if not managed:
            with owner_lock(paths.data, "desktop"):
                pass
        with owner_lock(paths.data, "server"):
            config = ConfigStore(paths.config).load()
            config = replace(config, mode="desktop" if managed else "server")
            with bind_socket(config) as listener:
                if not assets_available(paths.frontend):
                    raise ValueError(
                        "Production frontend assets missing or incomplete; "
                        "rebuild/install the application"
                    )
                command.upgrade(migration_config(paths.migrations, paths.database_url), "head")
                application = create_app(
                    database_url=paths.database_url,
                    frontend_path=paths.frontend,
                    runtime_paths=paths,
                    runtime_config=config,
                )
                handler = RotatingFileHandler(
                    paths.logs / "server.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
                )
                logger = logging.getLogger("uvicorn")
                logger.addHandler(handler)
                server = uvicorn.Server(
                    uvicorn.Config(
                        application,
                        host=config.bind,
                        port=config.port,
                        log_config=None,
                        access_log=False,
                        timeout_graceful_shutdown=5,
                    )
                )

                async def supervise() -> None:
                    task = asyncio.create_task(server.serve(sockets=[listener]))
                    try:
                        while not task.done():
                            if stopped.is_set():
                                server.should_exit = True
                            if server.started:
                                health = readiness(
                                    application.state.database, paths.frontend, paths.migrations
                                )
                                with application.state.database.sessions() as session:
                                    identity = SystemSettingsService(
                                        SqlAlchemySystemSettingsRepository(session)
                                    ).get_identity()
                                    radio = application.state.meshtastic_settings.status(
                                        SqlAlchemyChannelSettingsRepository(session)
                                    )
                                emit(
                                    {
                                        "state": "running"
                                        if health["status"] == "healthy"
                                        else "error",
                                        "health": health,
                                        "system_name": identity.system_name,
                                        "system_role": identity.system_role,
                                        "radio": f"Online via {radio.connection_type}"
                                        if radio.connected
                                        else "Offline",
                                        "urls": config.urls(),
                                    },
                                    output,
                                )
                            await asyncio.sleep(0.5 if not server.started else 2)
                        await task
                    finally:
                        server.should_exit = True
                        await task

                try:
                    asyncio.run(supervise())
                finally:
                    logger.removeHandler(handler)
                    handler.close()
        return 0
    except (OSError, ValueError, Timeout, CommandError) as error:
        emit({"state": "error", "error": str(error)}, output)
        return 1
