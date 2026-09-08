"""Filesystem and environment configuration."""

import os
from pathlib import Path

from solora.version import APP_VERSION as APP_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "solora.db"
DEFAULT_FRONTEND_PATH = PROJECT_ROOT / "frontend" / "dist"


def database_url() -> str:
    """Return the configured local database URL."""
    return os.getenv("SOLORA_DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE_PATH}")
