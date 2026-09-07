"""Integration tests for two virtual SOLoRa nodes."""

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config

from solora.adapters.persistence.database import Database
from solora.adapters.persistence.records import ThreadRecord
from solora.adapters.persistence.repository import SqlAlchemyForumRepository
from solora.adapters.persistence.sync_repository import SqlAlchemySyncRepository
from solora.adapters.transport.in_memory import InMemoryNetwork
from solora.application.sync import SyncNode
from solora.application.transport_ports import TrafficPriority
from solora.domain.protocol import MessageType, PacketEnvelope

ROOT = Path(__file__).resolve().parents[1]


class ManualClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 7, 12, 0, 0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def _migrate(database_url: str) -> None:
    config = Config(ROOT / "backend" / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def _id_factory(node: int) -> Callable[[], bytes]:
    sequence = 0

    def create() -> bytes:
        nonlocal sequence
        sequence += 1
        return node.to_bytes(4) + sequence.to_bytes(8)

    return create


def test_two_nodes_retry_loss_acknowledge_and_deduplicate(tmp_path: Path) -> None:
    url_a = f"sqlite:///{tmp_path / 'node-a.db'}"
    url_b = f"sqlite:///{tmp_path / 'node-b.db'}"
    _migrate(url_a)
    _migrate(url_b)
    database_a = Database(url_a)
    database_b = Database(url_b)
    clock = ManualClock()
    network = InMemoryNetwork()

    with database_a.sessions() as session_a, database_b.sessions() as session_b:
        shared_thread = SqlAlchemyForumRepository(session_a).create_thread("Gemensam tråd")
        assert shared_thread.sync_id is not None
        SqlAlchemyForumRepository(session_b).create_thread("Gemensam tråd")
        receiver_thread = session_b.get(ThreadRecord, 1)
        assert receiver_thread is not None
        receiver_thread.sync_id = bytes.fromhex(shared_thread.sync_id)
        session_b.commit()
        node_a = SyncNode(
            SqlAlchemySyncRepository(session_a),
            network.connect(0xA),
            clock=clock,
            id_factory=_id_factory(0xA),
        )
        node_b = SyncNode(
            SqlAlchemySyncRepository(session_b),
            network.connect(0xB),
            clock=clock,
            id_factory=_id_factory(0xB),
        )

        message_id = node_a.publish_post(1, "Post från nod A", destination=0xB)
        assert node_a.pending_count() == 1

        network.drop_next()
        assert node_a.flush() == 1
        before_retry = SqlAlchemyForumRepository(session_b).get_thread(1)
        assert before_retry is not None
        assert before_retry.post_count == 0
        assert node_a.pending_count() == 1
        assert node_a.flush() == 0

        clock.advance(2)
        assert node_a.flush() == 1
        received = SqlAlchemyForumRepository(session_b).get_thread(1)
        assert received is not None
        assert [post.body for post in received.posts] == ["Post från nod A"]
        assert received.posts[0].message_id == message_id.hex()
        assert node_a.pending_count() == 0
        assert node_a.stats.commit_acks == 1

        delivered_post = next(
            transmission
            for transmission in network.transmissions
            if transmission.delivered
            and PacketEnvelope.decode(transmission.frame.payload).message_type
            is MessageType.SYNC_POST
        )
        network.replay(delivered_post)

        after_duplicate = SqlAlchemyForumRepository(session_b).get_thread(1)
        assert after_duplicate is not None
        assert len(after_duplicate.posts) == 1
        assert node_b.stats.duplicate_posts == 1

    database_a.close()
    database_b.close()


def test_pending_outbox_survives_sender_restart(tmp_path: Path) -> None:
    url_a = f"sqlite:///{tmp_path / 'node-a.db'}"
    url_b = f"sqlite:///{tmp_path / 'node-b.db'}"
    _migrate(url_a)
    _migrate(url_b)
    clock = ManualClock()

    first_database = Database(url_a)
    first_network = InMemoryNetwork()
    with first_database.sessions() as session:
        shared_thread = SqlAlchemyForumRepository(session).create_thread("Gemensam tråd")
        assert shared_thread.sync_id is not None
        shared_sync_id = bytes.fromhex(shared_thread.sync_id)
        first_node = SyncNode(
            SqlAlchemySyncRepository(session),
            first_network.connect(0xA),
            clock=clock,
            id_factory=_id_factory(0xA),
        )
        first_node.publish_post(1, "Överlever omstart", destination=0xB)
        assert first_node.flush() == 1
        assert first_node.pending_count() == 1
    first_database.close()

    clock.advance(2)
    restarted_database = Database(url_a)
    receiver_database = Database(url_b)
    restarted_network = InMemoryNetwork()
    with restarted_database.sessions() as sender, receiver_database.sessions() as receiver:
        SqlAlchemyForumRepository(receiver).create_thread("Gemensam tråd")
        receiver_thread = receiver.get(ThreadRecord, 1)
        assert receiver_thread is not None
        receiver_thread.sync_id = shared_sync_id
        receiver.commit()
        restarted_node = SyncNode(
            SqlAlchemySyncRepository(sender),
            restarted_network.connect(0xA),
            clock=clock,
            id_factory=_id_factory(0xA),
        )
        SyncNode(
            SqlAlchemySyncRepository(receiver),
            restarted_network.connect(0xB),
            clock=clock,
            id_factory=_id_factory(0xB),
        )

        assert restarted_node.flush() == 1
        assert restarted_node.pending_count() == 0
        received = SqlAlchemyForumRepository(receiver).get_thread(1)
        assert received is not None
        assert [post.body for post in received.posts] == ["Överlever omstart"]

    restarted_database.close()
    receiver_database.close()


def test_idle_nodes_are_silent(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'node.db'}"
    _migrate(database_url)
    database = Database(database_url)
    network = InMemoryNetwork()
    with database.sessions() as session:
        node = SyncNode(SqlAlchemySyncRepository(session), network.connect(1))

        assert node.flush() == 0
        assert network.transmissions == []

    database.close()


def test_due_outbox_prioritizes_user_traffic(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'node.db'}"
    _migrate(database_url)
    database = Database(database_url)
    now = datetime(2026, 9, 7, 12, 0, 0)

    with database.sessions() as session:
        SqlAlchemyForumRepository(session).create_thread("Prioritering")
        repository = SqlAlchemySyncRepository(session)
        background_id = bytes.fromhex("010000000000000000000001")
        user_id = bytes.fromhex("020000000000000000000001")
        assert repository.publish_post(
            message_id=background_id,
            thread_id=1,
            body="Bakgrund",
            destination=2,
            frame=b"background",
            priority=TrafficPriority.BACKGROUND,
            now=now,
        )
        assert repository.publish_post(
            message_id=user_id,
            thread_id=1,
            body="Användare",
            destination=2,
            frame=b"user",
            priority=TrafficPriority.USER,
            now=now,
        )

        assert [entry.message_id for entry in repository.due_outbox(now)] == [
            user_id,
            background_id,
        ]

    database.close()
