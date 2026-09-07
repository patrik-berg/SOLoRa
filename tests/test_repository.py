"""Tests for the Phase 0 repository contract."""

from pathlib import Path


def test_required_project_structure_exists() -> None:
    root = Path(__file__).parents[1]
    required_paths = (
        "backend/src/solora",
        "frontend",
        "README.md",
        "ARCHITECTURE.md",
        "CHECKLIST.md",
        "PROTOCOL.md",
        "ROADMAP.md",
    )

    assert all((root / path).exists() for path in required_paths)
