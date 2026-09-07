"""Ports implemented by SOLoRa infrastructure adapters."""

from typing import Protocol

from solora.domain.models import Post, Thread


class ForumRepository(Protocol):
    """Persistence operations required by the forum use cases."""

    def list_threads(self) -> list[Thread]: ...

    def get_thread(self, thread_id: int) -> Thread | None: ...

    def create_thread(self, title: str) -> Thread: ...

    def create_post(self, thread_id: int, body: str) -> Post | None: ...
