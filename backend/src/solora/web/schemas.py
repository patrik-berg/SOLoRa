"""HTTP request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


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


class MeshtasticSettingsResponse(BaseModel):
    connected: bool
    node_id: int | None
    connection_type: str | None
    channels: list[MeshtasticChannelResponse]
    selection: MeshtasticChannelSelectionResponse | None
    selection_valid: bool
    recommended_channel_index: int | None
    error: str | None


class SelectMeshtasticChannelRequest(BaseModel):
    channel_index: int = Field(ge=0, le=7)
    channel_name: str = Field(max_length=12)
