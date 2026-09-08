"""Read-only browser summary. Never discover, reconnect, or transmit to a radio."""

from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from solora.adapters.persistence.database import Database
from solora.adapters.persistence.settings_repository import SqlAlchemyChannelSettingsRepository
from solora.adapters.persistence.system_settings_repository import (
    SqlAlchemySystemSettingsRepository,
)
from solora.application.meshtastic_settings import MeshtasticSettingsController
from solora.application.system_settings import SystemSettingsService
from solora.runtime.health import readiness
from solora.version import APP_VERSION


def browser_status(
    database: Database,
    controller: MeshtasticSettingsController,
    frontend: Path,
    migrations: Path,
) -> dict[str, object]:
    health = readiness(database, frontend, migrations)
    system: dict[str, object] | None = None
    node: dict[str, object] = {
        "connection_state": "unknown",
        "connection_type": None,
        "node_id": None,
    }
    try:
        with database.sessions() as session:
            identity = SystemSettingsService(
                SqlAlchemySystemSettingsRepository(session)
            ).get_identity()
            system = {"name": identity.system_name, "role": identity.system_role}
            radio = controller.status(SqlAlchemyChannelSettingsRepository(session))
            node = {
                "connection_state": "online" if radio.connected else "offline",
                "connection_type": radio.connection_type,
                "node_id": radio.node_id,
            }
    except (SQLAlchemyError, ValueError):
        # Broken state remains a reachable but degraded application, never fabricated radio state.
        health["status"] = "unhealthy"
    return {
        "application": {
            "state": "online" if health["status"] == "healthy" else "degraded",
            "version": APP_VERSION,
        },
        "system": system,
        "meshtastic": node,
        # Configured PRIMARY role is not evidence of active authority or a received heartbeat.
        "primary": {"node_id": None, "system_name": None, "last_heartbeat_at": None},
    }
