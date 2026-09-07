"""Local HTTP service entry point."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create the local SOLoRa web application."""
    application = FastAPI(title="SOLoRa", version="0.0.0")

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        """Report that the local service process is responsive."""
        return {"service": "solora", "status": "ok"}

    return application


app = create_app()
