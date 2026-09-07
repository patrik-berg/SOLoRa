"""Integration tests for the local HTTP service and SQLite persistence."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from solora.app import create_app

ROOT = Path(__file__).resolve().parents[1]


def _database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'solora-test.db'}"


def _migrate(database_url: str) -> None:
    config = Config(ROOT / "backend" / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def test_migration_creates_forum_schema(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)

    _migrate(database_url)

    tables = inspect(create_engine(database_url)).get_table_names()
    assert set(tables) >= {"alembic_version", "threads", "posts"}


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

        second_post = client.post(f"/api/threads/{thread_id}/posts", json={"body": "Ett svar"})
        assert second_post.status_code == 201

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
