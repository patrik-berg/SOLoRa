"""End-to-end tests for explicit hardware-independent forum repair."""

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from solora.adapters.persistence.database import Database
from solora.adapters.persistence.records import RepairRequestRecord
from solora.adapters.persistence.repository import SqlAlchemyForumRepository
from solora.adapters.persistence.sync_repository import SqlAlchemySyncRepository
from solora.adapters.transport.in_memory import InMemoryNetwork
from solora.application.sync import SyncNode
from solora.domain.protocol import MessageType, PacketEnvelope

ROOT = Path(__file__).resolve().parents[1]


class RepairClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 7, 12, 0, 0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int = 120) -> None:
        self.now += timedelta(seconds=seconds)


def _id_factory(node: int) -> Callable[[], bytes]:
    sequence = 10_000

    def create() -> bytes:
        nonlocal sequence
        sequence += 1
        return node.to_bytes(4) + sequence.to_bytes(8)

    return create


def _migrate(database_url: str) -> None:
    config = Config(ROOT / "backend" / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def _forum_contents(repository: SqlAlchemyForumRepository) -> dict[str, list[str]]:
    contents: dict[str, list[str]] = {}
    for summary in repository.list_threads():
        detail = repository.get_thread(summary.id)
        assert detail is not None
        contents[summary.title] = [post.body for post in detail.posts]
    return contents


def _drive(clock: RepairClock, *nodes: SyncNode, rounds: int = 12) -> None:
    for _ in range(rounds):
        for node in nodes:
            node.flush()
        clock.advance()


def test_offline_nodes_reconnect_repair_loss_and_converge_idempotently(
    tmp_path: Path,
) -> None:
    url_a = f"sqlite:///{tmp_path / 'node-a.db'}"
    url_b = f"sqlite:///{tmp_path / 'node-b.db'}"
    _migrate(url_a)
    _migrate(url_b)
    database_a = Database(url_a)
    database_b = Database(url_b)
    clock = RepairClock()

    with database_a.sessions() as session_a, database_b.sessions() as session_b:
        forum_a = SqlAlchemyForumRepository(session_a)
        forum_b = SqlAlchemyForumRepository(session_b)
        thread_a = forum_a.create_thread("Endast hos A")
        forum_a.create_post(thread_a.id, "A:s lokala inlägg")
        thread_b = forum_b.create_thread("Endast hos B")
        forum_b.create_post(thread_b.id, "B:s lokala inlägg")

        offline_network = InMemoryNetwork()
        offline_a = SyncNode(
            SqlAlchemySyncRepository(session_a),
            offline_network.connect(0xA),
            clock=clock,
            id_factory=_id_factory(0xA),
        )
        assert offline_a.request_sync(0xB) == 1
        assert offline_a.flush() == 1
        assert offline_a.pending_count() == 1

    clock.advance()
    network = InMemoryNetwork()
    with database_a.sessions() as session_a, database_b.sessions() as session_b:
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

        network.drop_next()
        _drive(clock, node_a, node_b)

        expected = {
            "Endast hos A": ["A:s lokala inlägg"],
            "Endast hos B": ["B:s lokala inlägg"],
        }
        assert _forum_contents(SqlAlchemyForumRepository(session_a)) == expected
        assert _forum_contents(SqlAlchemyForumRepository(session_b)) == expected
        assert node_a.pending_count() == 0
        assert node_b.pending_count() == 0
        assert session_a.scalar(select(func.count()).select_from(RepairRequestRecord)) == 0
        assert session_b.scalar(select(func.count()).select_from(RepairRequestRecord)) == 0

        delivered_types = {
            PacketEnvelope.decode(item.frame.payload).message_type
            for item in network.transmissions
            if item.delivered
        }
        assert delivered_types >= {
            MessageType.SYNC,
            MessageType.WANT,
            MessageType.THREAD,
            MessageType.SYNC_POST,
            MessageType.COMMIT_ACK,
        }

        before_a = _forum_contents(SqlAlchemyForumRepository(session_a))
        before_b = _forum_contents(SqlAlchemyForumRepository(session_b))
        assert node_b.request_sync(0xA) == 1
        _drive(clock, node_a, node_b)

        assert _forum_contents(SqlAlchemyForumRepository(session_a)) == before_a
        assert _forum_contents(SqlAlchemyForumRepository(session_b)) == before_b
        assert node_a.pending_count() == 0
        assert node_b.pending_count() == 0

    database_a.close()
    database_b.close()


def test_inventory_pages_repair_more_objects_than_one_frame(tmp_path: Path) -> None:
    url_a = f"sqlite:///{tmp_path / 'node-a.db'}"
    url_b = f"sqlite:///{tmp_path / 'node-b.db'}"
    _migrate(url_a)
    _migrate(url_b)
    database_a = Database(url_a)
    database_b = Database(url_b)
    clock = RepairClock()
    network = InMemoryNetwork()

    with database_a.sessions() as session_a, database_b.sessions() as session_b:
        forum_a = SqlAlchemyForumRepository(session_a)
        for index in range(18):
            forum_a.create_thread(f"Tråd {index:02d}")

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

        assert node_a.request_sync(0xB) == 2
        _drive(clock, node_a, node_b, rounds=20)

        assert len(SqlAlchemyForumRepository(session_b).list_threads()) == 18
        sync_frames = [
            item
            for item in network.transmissions
            if item.frame.source == 0xA
            and PacketEnvelope.decode(item.frame.payload).message_type is MessageType.SYNC
        ]
        assert len(sync_frames) == 2
        assert node_a.pending_count() == 0
        assert node_b.pending_count() == 0

    database_a.close()
    database_b.close()


def test_missing_thread_is_requested_before_post_is_committed(tmp_path: Path) -> None:
    url_a = f"sqlite:///{tmp_path / 'node-a.db'}"
    url_b = f"sqlite:///{tmp_path / 'node-b.db'}"
    _migrate(url_a)
    _migrate(url_b)
    database_a = Database(url_a)
    database_b = Database(url_b)
    clock = RepairClock()
    network = InMemoryNetwork()

    with database_a.sessions() as session_a, database_b.sessions() as session_b:
        forum_a = SqlAlchemyForumRepository(session_a)
        thread = forum_a.create_thread("Saknad tråd")
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

        node_a.publish_post(thread.id, "Väntar på tråden", destination=0xB)
        node_a.flush()
        assert SqlAlchemyForumRepository(session_b).list_threads() == []
        assert node_a.pending_count() == 1

        _drive(clock, node_b, node_a)

        assert _forum_contents(SqlAlchemyForumRepository(session_b)) == {
            "Saknad tråd": ["Väntar på tråden"]
        }
        assert node_a.pending_count() == 0
        assert node_b.pending_count() == 0

    database_a.close()
    database_b.close()
