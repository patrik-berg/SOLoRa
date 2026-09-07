"""Transport and persistence ports used by the synchronization service."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Protocol

from solora.domain.protocol import ObjectRef


class TrafficPriority(IntEnum):
    """Application scheduling priority, mapped by concrete transports."""

    BACKGROUND = 10
    USER = 100


@dataclass(frozen=True, slots=True)
class InboundFrame:
    """Bytes delivered by a transport with transport-owned addressing."""

    source: int
    destination: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class OutboxEntry:
    """A durable application frame waiting for commit acknowledgement."""

    message_id: bytes
    destination: int
    frame: bytes
    priority: TrafficPriority
    attempts: int
    next_attempt_at: datetime


class ReceiveResult(IntEnum):
    """Durable outcome of receiving an application message."""

    STORED = 1
    DUPLICATE = 2
    MISSING_THREAD = 3


@dataclass(frozen=True, slots=True)
class SyncObject:
    """One immutable forum object ready for wire encoding."""

    ref: ObjectRef
    content: str
    thread_sync_id: bytes | None = None


FrameReceiver = Callable[[InboundFrame], None]


class TransportError(RuntimeError):
    """Raised when a transport cannot accept a frame."""


class Transport(Protocol):
    """Minimal transport boundary; Meshtastic details stay in its adapter."""

    @property
    def node_id(self) -> int: ...

    def set_receiver(self, receiver: FrameReceiver) -> None: ...

    def send(
        self,
        destination: int,
        payload: bytes,
        *,
        priority: TrafficPriority,
    ) -> None: ...


class SyncRepository(Protocol):
    """Durable state required by the two-node synchronization service."""

    def publish_post(
        self,
        *,
        message_id: bytes,
        thread_id: int,
        body: str,
        destination: int,
        frame: bytes,
        priority: TrafficPriority,
        now: datetime,
    ) -> bool: ...

    def thread_sync_id(self, thread_id: int) -> bytes | None: ...

    def queue_frame(
        self,
        *,
        message_id: bytes,
        destination: int,
        frame: bytes,
        priority: TrafficPriority,
        now: datetime,
    ) -> bool: ...

    def due_outbox(self, now: datetime) -> list[OutboxEntry]: ...

    def record_attempt(
        self,
        message_id: bytes,
        *,
        next_attempt_at: datetime,
    ) -> None: ...

    def acknowledge(self, message_id: bytes, *, source: int) -> bool: ...

    def receive_post(
        self,
        *,
        message_id: bytes,
        source: int,
        thread_id: int,
        body: str,
        now: datetime,
    ) -> ReceiveResult: ...

    def receive_thread(
        self,
        *,
        sync_id: bytes,
        source: int,
        title: str,
        now: datetime,
    ) -> ReceiveResult: ...

    def receive_sync_post(
        self,
        *,
        message_id: bytes,
        source: int,
        thread_sync_id: bytes,
        body: str,
        now: datetime,
    ) -> ReceiveResult: ...

    def record_control_message(
        self,
        *,
        message_id: bytes,
        source: int,
        message_type: int,
        now: datetime,
    ) -> bool: ...

    def has_received(self, message_id: bytes) -> bool: ...

    def known_objects(self) -> list[ObjectRef]: ...

    def missing_objects(self, refs: tuple[ObjectRef, ...]) -> list[ObjectRef]: ...

    def get_sync_object(self, ref: ObjectRef) -> SyncObject | None: ...

    def queue_want(
        self,
        *,
        refs: tuple[ObjectRef, ...],
        message_id: bytes,
        destination: int,
        frame: bytes,
        now: datetime,
    ) -> bool: ...

    def unrequested_objects(
        self,
        refs: tuple[ObjectRef, ...],
        *,
        destination: int,
    ) -> list[ObjectRef]: ...

    def resolve_repair(self, ref: ObjectRef) -> None: ...

    def pending_count(self) -> int: ...
