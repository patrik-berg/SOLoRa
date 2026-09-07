"""Run the Phase 2 transport foundation with two virtual local nodes."""

from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config

from solora.adapters.persistence.database import Database
from solora.adapters.persistence.records import ThreadRecord
from solora.adapters.persistence.repository import SqlAlchemyForumRepository
from solora.adapters.persistence.sync_repository import SqlAlchemySyncRepository
from solora.adapters.transport.in_memory import InMemoryNetwork
from solora.application.sync import SyncNode
from solora.config import PROJECT_ROOT
from solora.domain.protocol import MessageType, PacketEnvelope


class DemoClock:
    """Controllable time keeps the retry demo instant and deterministic."""

    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, 0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def migrate(database_url: str) -> None:
    config = Config(PROJECT_ROOT / "backend" / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def run_demo() -> None:
    """Show loss, retry, commit acknowledgement, and deduplication."""
    with TemporaryDirectory(prefix="solora-two-node-") as directory:
        root = Path(directory)
        url_a = f"sqlite:///{root / 'node-a.db'}"
        url_b = f"sqlite:///{root / 'node-b.db'}"
        migrate(url_a)
        migrate(url_b)
        database_a = Database(url_a)
        database_b = Database(url_b)
        network = InMemoryNetwork()
        clock = DemoClock()

        with database_a.sessions() as session_a, database_b.sessions() as session_b:
            shared_thread = SqlAlchemyForumRepository(session_a).create_thread("Virtuell radiotråd")
            SqlAlchemyForumRepository(session_b).create_thread("Virtuell radiotråd")
            receiver_thread = session_b.get(ThreadRecord, 1)
            if receiver_thread is None or shared_thread.sync_id is None:
                raise RuntimeError("Demo thread setup failed")
            receiver_thread.sync_id = bytes.fromhex(shared_thread.sync_id)
            session_b.commit()
            node_a = SyncNode(
                SqlAlchemySyncRepository(session_a), network.connect(0xA), clock=clock
            )
            node_b = SyncNode(
                SqlAlchemySyncRepository(session_b), network.connect(0xB), clock=clock
            )

            message_id = node_a.publish_post(
                1,
                "Hej från virtuell nod A",
                destination=0xB,
            )
            print(f"Köad POST {message_id.hex()} på nod A; outbox={node_a.pending_count()}")

            network.drop_next()
            node_a.flush()
            print(f"Första sändningen tappades; outbox={node_a.pending_count()}")

            clock.advance(2)
            node_a.flush()
            thread_b = SqlAlchemyForumRepository(session_b).get_thread(1)
            post_count = thread_b.post_count if thread_b else 0
            print(
                f"Retry levererad och COMMIT_ACK mottagen; "
                f"outbox={node_a.pending_count()}, inlägg på B={post_count}"
            )

            delivered_post = next(
                transmission
                for transmission in network.transmissions
                if transmission.delivered
                and PacketEnvelope.decode(transmission.frame.payload).message_type
                is MessageType.SYNC_POST
            )
            network.replay(delivered_post)
            thread_b = SqlAlchemyForumRepository(session_b).get_thread(1)
            post_count = thread_b.post_count if thread_b else 0
            print(
                f"Samma frame spelades upp igen; inlägg på B={post_count}, "
                f"deduplicerade={node_b.stats.duplicate_posts}"
            )

        database_a.close()
        database_b.close()


if __name__ == "__main__":
    run_demo()
