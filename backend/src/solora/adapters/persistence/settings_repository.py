"""SQLite persistence for local Meshtastic channel selection."""

from sqlalchemy.orm import Session

from solora.adapters.persistence.records import (
    MeshtasticConnectionRecord,
    MeshtasticSettingsRecord,
)
from solora.domain.meshtastic_settings import (
    MeshtasticChannelSelection,
    MeshtasticConnectionConfig,
    MeshtasticConnectionType,
    MeshtasticSavedConnection,
)

SETTINGS_ID = 1
CONNECTION_ID = 1


class SqlAlchemyChannelSettingsRepository:
    """Store one confirmed channel binding without channel secrets."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_channel_selection(self) -> MeshtasticChannelSelection | None:
        record = self.session.get(MeshtasticSettingsRecord, SETTINGS_ID)
        if record is None:
            return None
        return MeshtasticChannelSelection(
            node_id=record.selected_node_id,
            channel_index=record.selected_channel_index,
            channel_name=record.selected_channel_name,
        )

    def save_channel_selection(self, selection: MeshtasticChannelSelection) -> None:
        record = self.session.get(MeshtasticSettingsRecord, SETTINGS_ID)
        if record is None:
            record = MeshtasticSettingsRecord(
                id=SETTINGS_ID,
                selected_node_id=selection.node_id,
                selected_channel_index=selection.channel_index,
                selected_channel_name=selection.channel_name,
            )
            self.session.add(record)
        else:
            record.selected_node_id = selection.node_id
            record.selected_channel_index = selection.channel_index
            record.selected_channel_name = selection.channel_name
        self.session.commit()

    def get_connection(self) -> MeshtasticSavedConnection | None:
        record = self.session.get(MeshtasticConnectionRecord, CONNECTION_ID)
        if record is None:
            return None
        return MeshtasticSavedConnection(
            config=MeshtasticConnectionConfig(
                connection_type=MeshtasticConnectionType(record.connection_type),
                endpoint=record.endpoint,
            ),
            node_id=record.node_id,
            node_name=record.node_name,
            firmware_version=record.firmware_version,
            last_contact=record.last_contact,
        )

    def save_connection(self, connection: MeshtasticSavedConnection) -> None:
        record = self.session.get(MeshtasticConnectionRecord, CONNECTION_ID)
        if record is None:
            record = MeshtasticConnectionRecord(id=CONNECTION_ID)
            self.session.add(record)
        record.connection_type = connection.config.connection_type
        record.endpoint = connection.config.endpoint
        record.node_id = connection.node_id
        record.node_name = connection.node_name
        record.firmware_version = connection.firmware_version
        record.last_contact = connection.last_contact
        self.session.commit()
