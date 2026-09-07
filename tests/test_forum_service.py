"""Unit tests for framework-independent forum rules."""

from datetime import UTC, datetime

import pytest

from solora.application.forum import ForumService, ForumValidationError, ThreadNotFoundError
from solora.domain.models import Post, Thread


class FakeForumRepository:
    def __init__(self) -> None:
        self.thread = Thread(1, "Rubrik", datetime.now(UTC), 0)

    def list_threads(self) -> list[Thread]:
        return [self.thread]

    def get_thread(self, thread_id: int) -> Thread | None:
        return self.thread if thread_id == self.thread.id else None

    def create_thread(self, title: str) -> Thread:
        return Thread(2, title, datetime.now(UTC), 0)

    def create_post(self, thread_id: int, body: str) -> Post | None:
        if thread_id != self.thread.id:
            return None
        return Post(1, thread_id, body, datetime.now(UTC))


def test_service_lists_and_reads_threads() -> None:
    service = ForumService(FakeForumRepository())

    assert service.list_threads()[0].title == "Rubrik"
    assert service.get_thread(1).id == 1

    with pytest.raises(ThreadNotFoundError):
        service.get_thread(999)


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_service_rejects_invalid_titles(title: str) -> None:
    with pytest.raises(ForumValidationError):
        ForumService(FakeForumRepository()).create_thread(title)


def test_service_normalizes_titles() -> None:
    created = ForumService(FakeForumRepository()).create_thread("  Ny rubrik  ")

    assert created.title == "Ny rubrik"


@pytest.mark.parametrize("body", ["", "   ", "x" * 4_001])
def test_service_rejects_invalid_posts(body: str) -> None:
    with pytest.raises(ForumValidationError):
        ForumService(FakeForumRepository()).create_post(1, body)


def test_service_normalizes_posts_and_rejects_unknown_thread() -> None:
    service = ForumService(FakeForumRepository())

    assert service.create_post(1, "  Lokalt svar  ").body == "Lokalt svar"
    with pytest.raises(ThreadNotFoundError):
        service.create_post(999, "Text")
