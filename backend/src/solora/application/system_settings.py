"""Use cases for explicit local system identity and role."""

from typing import Protocol

from solora.domain.system_settings import DEFAULT_SYSTEM_NAME, SystemIdentity, SystemRole


class SystemSettingsRepository(Protocol):
    def get_system_identity(self) -> SystemIdentity | None: ...

    def save_system_identity(self, identity: SystemIdentity) -> None: ...


class SystemSettingsValidationError(ValueError):
    """Raised for invalid system identity values."""


class RoleChangeConfirmationRequiredError(SystemSettingsValidationError):
    """Raised when a behavior-changing role update was not confirmed."""


class SystemSettingsService:
    """Manage display identity separately from explicit system behavior."""

    def __init__(self, repository: SystemSettingsRepository) -> None:
        self.repository = repository

    def get_identity(self) -> SystemIdentity:
        return self.repository.get_system_identity() or SystemIdentity(
            system_name=DEFAULT_SYSTEM_NAME,
            system_role=SystemRole.CLIENT,
        )

    def update_identity(
        self,
        *,
        system_name: str,
        system_role: SystemRole,
        confirm_role_change: bool,
    ) -> SystemIdentity:
        normalized_name = system_name.strip()
        if not normalized_name:
            raise SystemSettingsValidationError("System name must not be empty")
        if len(normalized_name) > 64:
            raise SystemSettingsValidationError("System name must be at most 64 characters")

        current = self.get_identity()
        if current.system_role is not system_role and not confirm_role_change:
            raise RoleChangeConfirmationRequiredError(
                "Changing system role requires explicit confirmation"
            )
        identity = SystemIdentity(normalized_name, system_role)
        self.repository.save_system_identity(identity)
        return identity
