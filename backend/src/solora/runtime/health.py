"""Readiness contract shared by HTTP and the desktop's local status pipe."""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from solora.adapters.persistence.database import Database
from solora.adapters.persistence.settings_repository import SqlAlchemyChannelSettingsRepository
from solora.adapters.persistence.system_settings_repository import (
    SqlAlchemySystemSettingsRepository,
)
from solora.application.system_settings import SystemSettingsService
from solora.domain.protocol import PROTOCOL_VERSION
from solora.version import APP_VERSION


def migration_config(migrations: Path, database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(migrations).replace("%", "%%"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["runtime_explicit_url"] = True
    return config


class AssetReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("src"):
            self.references.append(str(attributes["src"]))
        if tag == "link" and attributes.get("rel") in ("stylesheet", "modulepreload"):
            self.references.append(attributes.get("href") or "")


def assets_available(frontend: Path) -> bool:
    try:
        parser = AssetReferences()
        parser.feed((frontend / "index.html").read_text(encoding="utf-8"))
        if not parser.references:
            return False
        for reference in parser.references:
            url = urlsplit(reference)
            if url.scheme or url.netloc or not url.path:
                return False
            asset = (frontend / url.path.lstrip("/")).resolve()
            if frontend.resolve() not in asset.parents or not asset.is_file():
                return False
        return True
    except (OSError, ValueError):
        return False


def readiness(database: Database, frontend: Path, migrations: Path) -> dict[str, object]:
    checks = {
        "backend": True,
        "database": False,
        "migrations": False,
        "state": False,
        "frontend": assets_available(frontend),
    }
    try:
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            checks["database"] = True
            expected = ScriptDirectory.from_config(
                migration_config(migrations, str(database.engine.url))
            ).get_heads()
            checks["migrations"] = set(
                MigrationContext.configure(connection).get_current_heads()
            ) == set(expected)
        with database.sessions() as session:
            SystemSettingsService(SqlAlchemySystemSettingsRepository(session)).get_identity()
            repository = SqlAlchemyChannelSettingsRepository(session)
            repository.get_connection()
            repository.get_channel_selection()
            checks["state"] = True
    except (SQLAlchemyError, ValueError, OSError, CommandError):
        pass
    return {
        "service": "solora",
        "status": "healthy" if all(checks.values()) else "unhealthy",
        "contract_version": 1,
        "app_version": APP_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "checks": checks,
    }
