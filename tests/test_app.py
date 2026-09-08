"""Integration tests for the local HTTP service and SQLite persistence."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from solora.app import create_app
from solora.domain.meshtastic_settings import MeshtasticChannel, MeshtasticNodeChannels

ROOT = Path(__file__).resolve().parents[1]


def _database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'solora-test.db'}"


def _migrate(database_url: str, revision: str = "head") -> None:
    config = Config(ROOT / "backend" / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, revision)


def test_migration_creates_forum_schema(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    _migrate(database_url)

    tables = inspect(create_engine(database_url)).get_table_names()
    assert set(tables) >= {
        "alembic_version",
        "threads",
        "posts",
        "outbox",
        "received_messages",
        "repair_requests",
        "meshtastic_settings",
    }


def test_transport_migration_preserves_existing_posts(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _migrate(database_url, "20260907_0001")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO threads (title) VALUES ('Befintlig tråd')"))
        connection.execute(text("INSERT INTO posts (thread_id, body) VALUES (1, 'Sparad text')"))

    _migrate(database_url)

    with engine.connect() as connection:
        saved_post = connection.execute(
            text("SELECT body, length(message_id) FROM posts WHERE id = 1")
        ).one()
        saved_thread = connection.execute(
            text("SELECT title, length(sync_id) FROM threads WHERE id = 1")
        ).one()
    assert saved_post == ("Sparad text", 12)
    assert saved_thread == ("Befintlig tråd", 12)


def test_forum_api_persists_threads_and_posts(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _migrate(database_url)

    with TestClient(create_app(database_url=database_url)) as client:
        assert client.get("/health").json() == {
            "service": "solora",
            "status": "ok",
        }
        assert client.get("/api/threads").json() == []

        created = client.post("/api/threads", json={"title": "  Första tråden  "})
        assert created.status_code == 201
        thread_id = created.json()["id"]
        assert created.json()["title"] == "Första tråden"
        assert created.json()["post_count"] == 0

        posted = client.post(
            f"/api/threads/{thread_id}/posts", json={"body": "  Första inlägget  "}
        )
        assert posted.status_code == 201
        assert posted.json()["body"] == "Första inlägget"
        assert len(posted.json()["message_id"]) == 24

        second_post = client.post(f"/api/threads/{thread_id}/posts", json={"body": "Ett svar"})
        assert second_post.status_code == 201
        assert second_post.json()["message_id"] != posted.json()["message_id"]

        detail = client.get(f"/api/threads/{thread_id}")
        assert detail.status_code == 200
        assert [post["body"] for post in detail.json()["posts"]] == [
            "Första inlägget",
            "Ett svar",
        ]
        assert client.get("/api/threads").json()[0]["post_count"] == 2

    # A new application and connection must see the same on-disk data.
    with TestClient(create_app(database_url=database_url)) as restarted_client:
        persisted = restarted_client.get(f"/api/threads/{thread_id}")
        assert persisted.status_code == 200
        assert len(persisted.json()["posts"]) == 2


def test_forum_api_validates_input_and_missing_threads(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _migrate(database_url)

    with TestClient(create_app(database_url=database_url)) as client:
        assert client.post("/api/threads", json={"title": "   ", "body": "text"}).status_code == 400
        assert client.get("/api/threads/999").status_code == 404
        assert client.post("/api/threads/999/posts", json={"body": "text"}).status_code == 404

        created = client.post("/api/threads", json={"title": "Rubrik", "body": "Start"})
        assert (
            client.post(
                f"/api/threads/{created.json()['id']}/posts", json={"body": "   "}
            ).status_code
            == 400
        )


def test_built_frontend_is_served(tmp_path: Path) -> None:
    frontend_path = tmp_path / "dist"
    frontend_path.mkdir()
    (frontend_path / "index.html").write_text("<h1>SOLoRa frontend</h1>", encoding="utf-8")

    with TestClient(
        create_app(database_url="sqlite:///:memory:", frontend_path=frontend_path)
    ) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "SOLoRa frontend" in response.text


class FakeChannelDiscovery:
    def __init__(self) -> None:
        self.calls = 0
        self.node_id = 0xA1
        self.channels: tuple[MeshtasticChannel, ...] = (
            MeshtasticChannel(0, "Primary", "primary"),
            MeshtasticChannel(3, "solora-link", "secondary"),
        )

    def discover(self) -> MeshtasticNodeChannels:
        self.calls += 1
        return MeshtasticNodeChannels(self.node_id, "serial", self.channels)


def test_meshtastic_channel_selection_is_explicit_persistent_and_silent(
    tmp_path: Path,
) -> None:
    database_url = _database_url(tmp_path)
    _migrate(database_url)
    discovery = FakeChannelDiscovery()

    with TestClient(create_app(database_url=database_url, channel_discovery=discovery)) as client:
        initial = client.get("/api/settings/meshtastic").json()
        assert discovery.calls == 0
        assert initial["connected"] is False

        refreshed = client.post("/api/settings/meshtastic/refresh").json()
        assert discovery.calls == 1
        assert refreshed["recommended_channel_index"] == 3
        assert "psk" not in str(refreshed).lower()

        selected = client.put(
            "/api/settings/meshtastic/channel",
            json={"channel_index": 3, "channel_name": "solora-link"},
        ).json()
        assert selected["selection_valid"] is True

    restarted_discovery = FakeChannelDiscovery()
    with TestClient(
        create_app(database_url=database_url, channel_discovery=restarted_discovery)
    ) as client:
        saved = client.get("/api/settings/meshtastic").json()
        assert restarted_discovery.calls == 0
        assert saved["selection"]["channel_index"] == 3
        assert saved["selection_valid"] is False


def test_channel_move_or_node_change_requires_explicit_reconfirmation(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    _migrate(database_url)
    discovery = FakeChannelDiscovery()
    with TestClient(create_app(database_url=database_url, channel_discovery=discovery)) as client:
        client.post("/api/settings/meshtastic/refresh")
        client.put(
            "/api/settings/meshtastic/channel",
            json={"channel_index": 3, "channel_name": "solora-link"},
        )

        discovery.channels = (MeshtasticChannel(1, "solora-link", "secondary"),)
        moved = client.post("/api/settings/meshtastic/refresh").json()
        assert moved["selection_valid"] is False
        assert "moved" in moved["error"]

        stale_save = client.put(
            "/api/settings/meshtastic/channel",
            json={"channel_index": 3, "channel_name": "solora-link"},
        )
        assert stale_save.status_code == 409

        changed = client.put(
            "/api/settings/meshtastic/channel",
            json={"channel_index": 1, "channel_name": "solora-link"},
        ).json()
        assert changed["selection_valid"] is True
        assert changed["selection"]["channel_index"] == 1

        discovery.node_id = 0xB2
        changed_node = client.post("/api/settings/meshtastic/refresh").json()
        assert changed_node["selection_valid"] is False
        assert "differs" in changed_node["error"]
