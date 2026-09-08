"""HTTP routes for the local forum."""

from collections.abc import Iterator
from datetime import UTC
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status

from solora.adapters.persistence.database import Database
from solora.adapters.persistence.repository import SqlAlchemyForumRepository
from solora.adapters.persistence.settings_repository import SqlAlchemyChannelSettingsRepository
from solora.adapters.persistence.system_settings_repository import (
    SqlAlchemySystemSettingsRepository,
)
from solora.application.forum import ForumService, ForumValidationError, ThreadNotFoundError
from solora.application.meshtastic_settings import (
    ChannelSelectionError,
    MeshtasticSettingsController,
    MeshtasticSettingsStatus,
)
from solora.application.system_settings import (
    RoleChangeConfirmationRequiredError,
    SystemSettingsService,
    SystemSettingsValidationError,
)
from solora.config import APP_VERSION
from solora.domain.meshtastic_settings import RECOMMENDED_CHANNEL_NAME, MeshtasticConnectionConfig
from solora.domain.models import Post, Thread
from solora.domain.protocol import PROTOCOL_VERSION
from solora.domain.system_settings import SystemIdentity, SystemRole, primary_authority_identity
from solora.web.schemas import (
    CreatePostRequest,
    CreateThreadRequest,
    MeshtasticChannelResponse,
    MeshtasticChannelSelectionResponse,
    MeshtasticConnectionResponse,
    MeshtasticDeviceResponse,
    MeshtasticSettingsResponse,
    PostResponse,
    SelectMeshtasticChannelRequest,
    SystemSettingsResponse,
    TestMeshtasticConnectionRequest,
    ThreadResponse,
    ThreadSummaryResponse,
    UpdateSystemSettingsRequest,
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


def _system_repository(request: Request) -> Iterator[SqlAlchemySystemSettingsRepository]:
    database: Database = request.app.state.database
    with database.sessions() as session:
        yield SqlAlchemySystemSettingsRepository(session)


SystemRepositoryDependency = Annotated[
    SqlAlchemySystemSettingsRepository, Depends(_system_repository)
]


def _settings_controller(request: Request) -> MeshtasticSettingsController:
    return cast(MeshtasticSettingsController, request.app.state.meshtastic_settings)


SettingsControllerDependency = Annotated[
    MeshtasticSettingsController, Depends(_settings_controller)
]


def _settings(status_value: MeshtasticSettingsStatus) -> MeshtasticSettingsResponse:
    selection = status_value.selection
    last_contact = status_value.last_contact
    if last_contact is not None and last_contact.tzinfo is None:
        last_contact = last_contact.replace(tzinfo=UTC)
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
        devices=[
            MeshtasticDeviceResponse(
                path=device.path,
                label=device.label,
                connection_type=device.connection_type,
            )
            for device in status_value.devices
        ],
        connection=(
            MeshtasticConnectionResponse(
                connection_type=status_value.connection.connection_type,
                endpoint=status_value.connection.endpoint,
            )
            if status_value.connection is not None
            else None
        ),
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
        node_name=status_value.node_name,
        firmware_version=status_value.firmware_version,
        last_contact=last_contact,
        error=status_value.error,
    )


def _system_settings(
    identity: SystemIdentity,
    node_id: int | None,
) -> SystemSettingsResponse:
    authority = primary_authority_identity(identity, node_id)
    return SystemSettingsResponse(
        system_name=identity.system_name,
        system_role=identity.system_role,
        role_status="active" if identity.system_role is SystemRole.CLIENT else "experimental",
        meshtastic_node_id=node_id,
        primary_authority_node_id=authority.node_id if authority is not None else None,
        app_version=APP_VERSION,
        protocol_version=PROTOCOL_VERSION,
    )


@router.get("/settings/system", response_model=SystemSettingsResponse)
def get_system_settings(
    system_repository: SystemRepositoryDependency,
    channel_repository: ChannelRepositoryDependency,
) -> SystemSettingsResponse:
    identity = SystemSettingsService(system_repository).get_identity()
    connection = channel_repository.get_connection()
    return _system_settings(identity, connection.node_id if connection else None)


@router.put("/settings/system", response_model=SystemSettingsResponse)
def update_system_settings(
    request: UpdateSystemSettingsRequest,
    system_repository: SystemRepositoryDependency,
    channel_repository: ChannelRepositoryDependency,
) -> SystemSettingsResponse:
    try:
        identity = SystemSettingsService(system_repository).update_identity(
            system_name=request.system_name,
            system_role=request.system_role,
            confirm_role_change=request.confirm_role_change,
        )
    except RoleChangeConfirmationRequiredError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except SystemSettingsValidationError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    connection = channel_repository.get_connection()
    return _system_settings(identity, connection.node_id if connection else None)


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
    """Explicitly reconnect to the saved USB, serial, or network node."""
    return _settings(controller.refresh(repository))


@router.post("/settings/meshtastic/devices/refresh", response_model=MeshtasticSettingsResponse)
def refresh_meshtastic_devices(
    repository: ChannelRepositoryDependency,
    controller: SettingsControllerDependency,
) -> MeshtasticSettingsResponse:
    """List serial endpoints without opening them or transmitting radio traffic."""
    return _settings(controller.refresh_devices(repository))


@router.post("/settings/meshtastic/test", response_model=MeshtasticSettingsResponse)
def test_meshtastic_connection(
    request: TestMeshtasticConnectionRequest,
    repository: ChannelRepositoryDependency,
    controller: SettingsControllerDependency,
) -> MeshtasticSettingsResponse:
    """Explicitly connect to one endpoint and read its public node information."""
    return _settings(
        controller.test_connection(
            repository,
            MeshtasticConnectionConfig(
                connection_type=request.connection_type,
                endpoint=request.endpoint.strip(),
            ),
        )
    )


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
