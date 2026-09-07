"""HTTP routes for the local forum."""

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status

from solora.adapters.persistence.database import Database
from solora.adapters.persistence.repository import SqlAlchemyForumRepository
from solora.adapters.persistence.settings_repository import SqlAlchemyChannelSettingsRepository
from solora.application.forum import ForumService, ForumValidationError, ThreadNotFoundError
from solora.application.meshtastic_settings import (
    ChannelSelectionError,
    MeshtasticSettingsController,
    MeshtasticSettingsStatus,
)
from solora.domain.meshtastic_settings import RECOMMENDED_CHANNEL_NAME
from solora.domain.models import Post, Thread
from solora.web.schemas import (
    CreatePostRequest,
    CreateThreadRequest,
    MeshtasticChannelResponse,
    MeshtasticChannelSelectionResponse,
    MeshtasticSettingsResponse,
    PostResponse,
    SelectMeshtasticChannelRequest,
    ThreadResponse,
    ThreadSummaryResponse,
)

router = APIRouter(prefix="/api")


def _repository(request: Request) -> Iterator[SqlAlchemyForumRepository]:
    database: Database = request.app.state.database
    with database.sessions() as session:
        yield SqlAlchemyForumRepository(session)


RepositoryDependency = Annotated[SqlAlchemyForumRepository, Depends(_repository)]


def _channel_repository(request: Request) -> Iterator[SqlAlchemyChannelSettingsRepository]:
    database: Database = request.app.state.database
    with database.sessions() as session:
        yield SqlAlchemyChannelSettingsRepository(session)


ChannelRepositoryDependency = Annotated[
    SqlAlchemyChannelSettingsRepository, Depends(_channel_repository)
]


def _settings_controller(request: Request) -> MeshtasticSettingsController:
    return cast(MeshtasticSettingsController, request.app.state.meshtastic_settings)


SettingsControllerDependency = Annotated[
    MeshtasticSettingsController, Depends(_settings_controller)
]


def _settings(status_value: MeshtasticSettingsStatus) -> MeshtasticSettingsResponse:
    selection = status_value.selection
    return MeshtasticSettingsResponse(
        connected=status_value.connected,
        node_id=status_value.node_id,
        connection_type=status_value.connection_type,
        channels=[
            MeshtasticChannelResponse(
                index=channel.index,
                name=channel.name,
                display_name=channel.display_name,
                role=channel.role,
                recommended=channel.name.casefold() == RECOMMENDED_CHANNEL_NAME,
            )
            for channel in status_value.channels
        ],
        selection=(
            MeshtasticChannelSelectionResponse(
                node_id=selection.node_id,
                channel_index=selection.channel_index,
                channel_name=selection.channel_name,
            )
            if selection is not None
            else None
        ),
        selection_valid=status_value.selection_valid,
        recommended_channel_index=status_value.recommended_channel_index,
        error=status_value.error,
    )


@router.get("/settings/meshtastic", response_model=MeshtasticSettingsResponse)
def get_meshtastic_settings(
    repository: ChannelRepositoryDependency,
    controller: SettingsControllerDependency,
) -> MeshtasticSettingsResponse:
    """Return cached channel state without contacting a radio."""
    return _settings(controller.status(repository))


@router.post("/settings/meshtastic/refresh", response_model=MeshtasticSettingsResponse)
def refresh_meshtastic_settings(
    repository: ChannelRepositoryDependency,
    controller: SettingsControllerDependency,
) -> MeshtasticSettingsResponse:
    """Explicitly discover enabled channels from the serial node."""
    return _settings(controller.refresh(repository))


@router.put("/settings/meshtastic/channel", response_model=MeshtasticSettingsResponse)
def select_meshtastic_channel(
    request: SelectMeshtasticChannelRequest,
    repository: ChannelRepositoryDependency,
    controller: SettingsControllerDependency,
) -> MeshtasticSettingsResponse:
    try:
        return _settings(
            controller.select(
                repository,
                channel_index=request.channel_index,
                channel_name=request.channel_name,
            )
        )
    except ChannelSelectionError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


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
        message_id=post.message_id,
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
