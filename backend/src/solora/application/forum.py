"""Local forum use cases."""

from solora.application.ports import ForumRepository
from solora.domain.models import Post, Thread


class ForumValidationError(ValueError):
    """Raised when forum input violates a domain constraint."""


class ThreadNotFoundError(LookupError):
    """Raised when a requested thread does not exist."""


class ForumService:
    """Coordinate forum behavior independently of HTTP and SQLite."""

    def __init__(self, repository: ForumRepository) -> None:
        self.repository = repository

    def list_threads(self) -> list[Thread]:
        return self.repository.list_threads()

    def get_thread(self, thread_id: int) -> Thread:
        thread = self.repository.get_thread(thread_id)
        if thread is None:
            raise ThreadNotFoundError(thread_id)
        return thread

    def create_thread(self, title: str) -> Thread:
        normalized_title = title.strip()
        if not normalized_title:
            raise ForumValidationError("Title must not be empty")
        if len(normalized_title) > 200:
            raise ForumValidationError("Title must be at most 200 characters")
        return self.repository.create_thread(normalized_title)

    def create_post(self, thread_id: int, body: str) -> Post:
        normalized_body = body.strip()
        if not normalized_body:
            raise ForumValidationError("Post must not be empty")
        if len(normalized_body) > 4_000:
            raise ForumValidationError("Post must be at most 4000 characters")

        post = self.repository.create_post(thread_id, normalized_body)
        if post is None:
            raise ThreadNotFoundError(thread_id)
        return post
