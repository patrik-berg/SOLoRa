"""SQLite persistence for the local SOLoRa system identity."""

from sqlalchemy.orm import Session

from solora.adapters.persistence.records import SystemSettingsRecord
from solora.domain.system_settings import SystemIdentity, SystemRole

SYSTEM_SETTINGS_ID = 1


class SqlAlchemySystemSettingsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_system_identity(self) -> SystemIdentity | None:
        record = self.session.get(SystemSettingsRecord, SYSTEM_SETTINGS_ID)
        if record is None:
            return None
        return SystemIdentity(record.system_name, SystemRole(record.system_role))

    def save_system_identity(self, identity: SystemIdentity) -> None:
        record = self.session.get(SystemSettingsRecord, SYSTEM_SETTINGS_ID)
        if record is None:
            record = SystemSettingsRecord(
                id=SYSTEM_SETTINGS_ID,
                system_name=identity.system_name,
                system_role=identity.system_role,
            )
            self.session.add(record)
        else:
            record.system_name = identity.system_name
            record.system_role = identity.system_role
        self.session.commit()
