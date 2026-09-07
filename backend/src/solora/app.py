"""Local HTTP service entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from solora import __version__
from solora.adapters.persistence.database import Database
from solora.config import DEFAULT_FRONTEND_PATH
from solora.config import database_url as default_database_url
from solora.web.routes import router


def create_app(
    *,
    database_url: str | None = None,
    frontend_path: Path | None = None,
) -> FastAPI:
    """Create the local SOLoRa web application."""
    database = Database(database_url or default_database_url())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        database.close()

    application = FastAPI(title="SOLoRa", version=__version__, lifespan=lifespan)
    application.state.database = database
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Report that the local service process is responsive."""
        return {"service": "solora", "status": "ok"}

    static_path = frontend_path if frontend_path is not None else DEFAULT_FRONTEND_PATH
    if static_path.is_dir():
        application.mount("/", StaticFiles(directory=static_path, html=True), name="frontend")

    return application


app = create_app()
