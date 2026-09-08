"""SQLite persistence for local Meshtastic channel selection."""

from sqlalchemy.orm import Session

from solora.adapters.persistence.records import MeshtasticSettingsRecord
from solora.domain.meshtastic_settings import MeshtasticChannelSelection

SETTINGS_ID = 1


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
