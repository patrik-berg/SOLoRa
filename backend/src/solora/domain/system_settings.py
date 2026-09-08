"""Local system identity, independent from radio identity and display naming."""

from dataclasses import dataclass
from enum import StrEnum

DEFAULT_SYSTEM_NAME = "SOLoRa Node"


class SystemRole(StrEnum):
    CLIENT = "CLIENT"
    PRIMARY = "PRIMARY"
    BACKUP = "BACKUP"


@dataclass(frozen=True, slots=True)
class SystemIdentity:
    """User-managed local display name and explicit behavior role."""

    system_name: str
    system_role: SystemRole


@dataclass(frozen=True, slots=True)
class AuthorityIdentity:
    """Protocol-facing authority identity; display names are intentionally absent."""

    system_role: SystemRole
    node_id: int


def primary_authority_identity(
    identity: SystemIdentity,
    node_id: int | None,
) -> AuthorityIdentity | None:
    """Identify a configured primary only by explicit role and Meshtastic node ID."""
    if identity.system_role is not SystemRole.PRIMARY or node_id is None:
        return None
    return AuthorityIdentity(system_role=identity.system_role, node_id=node_id)
