"""HTTP routes for the local forum."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from solora.adapters.persistence.database import Database
from solora.adapters.persistence.repository import SqlAlchemyForumRepository
from solora.application.forum import ForumService, ForumValidationError, ThreadNotFoundError
from solora.domain.models import Post, Thread
from solora.web.schemas import (
    CreatePostRequest,
    CreateThreadRequest,
    PostResponse,
    ThreadResponse,
    ThreadSummaryResponse,
)

router = APIRouter(prefix="/api")


def _repository(request: Request) -> Iterator[SqlAlchemyForumRepository]:
    database: Database = request.app.state.database
    with database.sessions() as session:
        yield SqlAlchemyForumRepository(session)


RepositoryDependency = Annotated[SqlAlchemyForumRepository, Depends(_repository)]


def _summary(thread: Thread) -> ThreadSummaryResponse:
    return ThreadSummaryResponse(
        id=thread.id,
        title=thread.title,
        created_at=thread.created_at,
        post_count=thread.post_count,
    )


def _post(post: Post) -> PostResponse:
    return PostResponse(
        id=post.id,
        thread_id=post.thread_id,
        body=post.body,
        created_at=post.created_at,
    )


@router.get("/threads", response_model=list[ThreadSummaryResponse])
def list_threads(repository: RepositoryDependency) -> list[ThreadSummaryResponse]:
    return [_summary(thread) for thread in ForumService(repository).list_threads()]


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
def get_thread(thread_id: int, repository: RepositoryDependency) -> ThreadResponse:
    try:
        thread = ForumService(repository).get_thread(thread_id)
    except ThreadNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found") from error

    return ThreadResponse(
        **_summary(thread).model_dump(), posts=[_post(post) for post in thread.posts]
    )


@router.post(
    "/threads",
    response_model=ThreadSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_thread(
    request: CreateThreadRequest,
    repository: RepositoryDependency,
) -> ThreadSummaryResponse:
    try:
        thread = ForumService(repository).create_thread(request.title)
    except ForumValidationError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    return _summary(thread)


@router.post(
    "/threads/{thread_id}/posts",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_post(
    thread_id: int,
    request: CreatePostRequest,
    repository: RepositoryDependency,
) -> PostResponse:
    try:
        post = ForumService(repository).create_post(thread_id, request.body)
    except ForumValidationError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    except ThreadNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found") from error
    return _post(post)
