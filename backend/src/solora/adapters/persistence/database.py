"""SQLAlchemy database setup."""

from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class for persisted records."""


class Database:
    """Own the SQLAlchemy engine and session factory."""

    def __init__(self, url: str) -> None:
        if url.startswith("sqlite:///"):
            database_path = Path(url.removeprefix("sqlite:///"))
            if database_path != Path(":memory:"):
                database_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine: Engine = create_engine(
            url,
            connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
        )
        self.sessions: sessionmaker[Session] = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

    def close(self) -> None:
        """Release database connections."""
        self.engine.dispose()
