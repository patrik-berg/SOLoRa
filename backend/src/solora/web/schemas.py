"""HTTP request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from solora.domain.meshtastic_settings import MeshtasticConnectionType
from solora.domain.system_settings import SystemRole


class CreateThreadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class CreatePostRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4_000)


class ThreadSummaryResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    post_count: int


class PostResponse(BaseModel):
    id: int
    thread_id: int
    body: str
    created_at: datetime
    message_id: str | None


class ThreadResponse(ThreadSummaryResponse):
    posts: list[PostResponse]


class MeshtasticChannelResponse(BaseModel):
    index: int
    name: str
    display_name: str
    role: str
    recommended: bool


class MeshtasticChannelSelectionResponse(BaseModel):
    node_id: int
    channel_index: int
    channel_name: str


class MeshtasticDeviceResponse(BaseModel):
    path: str
    label: str
    connection_type: MeshtasticConnectionType


class MeshtasticConnectionResponse(BaseModel):
    connection_type: MeshtasticConnectionType
    endpoint: str


class MeshtasticSettingsResponse(BaseModel):
    connected: bool
    node_id: int | None
    connection_type: str | None
    channels: list[MeshtasticChannelResponse]
    devices: list[MeshtasticDeviceResponse]
    connection: MeshtasticConnectionResponse | None
    selection: MeshtasticChannelSelectionResponse | None
    selection_valid: bool
    recommended_channel_index: int | None
    node_name: str | None
    firmware_version: str | None
    last_contact: datetime | None
    mesh_status: str = "not_evaluated"
    error: str | None


class SelectMeshtasticChannelRequest(BaseModel):
    channel_index: int = Field(ge=0, le=7)
    channel_name: str = Field(max_length=12)


class TestMeshtasticConnectionRequest(BaseModel):
    connection_type: MeshtasticConnectionType
    endpoint: str = Field(min_length=1, max_length=255)

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_not_be_blank(cls, value: str) -> str:
        endpoint = value.strip()
        if not endpoint:
            raise ValueError("endpoint must not be blank")
        return endpoint


class SystemSettingsResponse(BaseModel):
    system_name: str
    system_role: SystemRole
    role_status: str
    meshtastic_node_id: int | None
    primary_authority_node_id: int | None
    app_version: str
    protocol_version: int


class UpdateSystemSettingsRequest(BaseModel):
    system_name: str = Field(min_length=1, max_length=64)
    system_role: SystemRole
    confirm_role_change: bool = False
