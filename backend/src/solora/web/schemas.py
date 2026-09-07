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


class ThreadResponse(ThreadSummaryResponse):
    posts: list[PostResponse]
