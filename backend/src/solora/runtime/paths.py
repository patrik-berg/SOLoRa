"""Persistent OS paths, independent of replaceable application resources."""

import sys
from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs

from solora.config import PROJECT_ROOT


@dataclass(frozen=True)
class RuntimePaths:
    application: Path
    data: Path
    config: Path
    logs: Path
    runtime: Path

    @classmethod
    def discover(cls, profile: Path | None = None) -> "RuntimePaths":
        resources = getattr(sys, "_MEIPASS", None)
        application = Path(resources) if resources else PROJECT_ROOT
        if profile is not None:
            root = profile.expanduser().resolve()
            return cls(application, root / "data", root / "config", root / "logs", root / "run")
        dirs = PlatformDirs("SOLoRa", appauthor=False, roaming=False)
        return cls(
            application,
            dirs.user_data_path / "data",
            dirs.user_config_path / "config",
            dirs.user_log_path,
            dirs.user_cache_path / "run",
        )

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data / 'solora.db'}"

    @property
    def frontend(self) -> Path:
        return self.application / "frontend" / "dist"

    @property
    def migrations(self) -> Path:
        return self.application / "backend" / "migrations"

    def prepare(self) -> None:
        for directory in (self.data, self.config, self.logs, self.runtime):
            resolved = directory.resolve()
            if (
                resolved == self.application.resolve()
                or self.application.resolve() in resolved.parents
            ):
                raise ValueError("Persistent paths must be outside application files")
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
