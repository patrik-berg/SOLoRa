"""Tests for deterministic beta versioning and release packaging."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.beta_release import (
    ReleaseError,
    build_bundle,
    next_beta_version,
    parse_beta_version,
    stage_version,
)


def test_next_beta_version_ignores_other_release_lines() -> None:
    version = next_beta_version(
        "0.2.0",
        ["v0.2.0-beta.2", "v0.1.0-beta.9", "v0.2.0", "not-a-version"],
    )

    assert version.tag == "v0.2.0-beta.3"
    assert version.python == "0.2.0b3"


@pytest.mark.parametrize("value", ["1.2.3", "0.02.0", "v0.2.0", "0.2"])
def test_next_beta_version_rejects_invalid_base(value: str) -> None:
    with pytest.raises(ReleaseError):
        next_beta_version(value, [])


def test_stage_version_updates_all_build_metadata(tmp_path: Path) -> None:
    (tmp_path / "backend/src/solora").mkdir(parents=True)
    (tmp_path / "frontend").mkdir()
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    (tmp_path / "backend/src/solora/__init__.py").write_text('__version__ = "0.1.0"\n')
    (tmp_path / "frontend/package.json").write_text(
        json.dumps({"name": "solora-frontend", "version": "0.1.0"})
    )

    stage_version(tmp_path, parse_beta_version("v0.2.0-beta.4"))

    assert 'version = "0.2.0b4"' in (tmp_path / "pyproject.toml").read_text()
    assert '__version__ = "0.2.0b4"' in (tmp_path / "backend/src/solora/__init__.py").read_text()
    assert json.loads((tmp_path / "frontend/package.json").read_text())["version"] == (
        "0.2.0-beta.4"
    )


def test_build_bundle_contains_runtime_and_matching_manifest(tmp_path: Path) -> None:
    version = parse_beta_version("v0.2.0-beta.1")
    _write(tmp_path, f"dist/solora-{version.python}-py3-none-any.whl", b"wheel")
    _write(tmp_path, f"dist/solora-{version.python}.tar.gz", b"source")
    _write(tmp_path, "frontend/dist/index.html", b"<h1>SOLoRa</h1>")
    _write(tmp_path, "frontend/dist/assets/app.js", b"app")
    _write(tmp_path, "backend/alembic.ini", b"[alembic]")
    _write(tmp_path, "backend/migrations/env.py", b"# migration")
    for name in ("README.md", "ARCHITECTURE.md", "PROTOCOL.md"):
        _write(tmp_path, name, name.encode())

    bundle, manifest_path = build_bundle(
        tmp_path,
        tmp_path / "release",
        version,
        commit="a" * 40,
        repository="patrik-berg/SOLoRa",
    )

    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert "manage.py" in names
        assert "BETA_README.md" in names
        assert "backend/alembic.ini" in names
        assert "backend/migrations/env.py" in names
        assert "frontend/dist/index.html" in names
        assert archive.read("VERSION") == b"v0.2.0-beta.1\n"

    manifest = json.loads(manifest_path.read_text())
    asset = manifest["assets"][0]
    assert manifest["channel"] == "beta"
    assert manifest["stable"] is False
    assert manifest["commit"] == "a" * 40
    assert asset["name"] == bundle.name
    assert asset["sha256"] == hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert asset["size"] == bundle.stat().st_size


def test_build_bundle_rejects_missing_output(tmp_path: Path) -> None:
    with pytest.raises(ReleaseError, match="Missing build output"):
        build_bundle(
            tmp_path,
            tmp_path / "release",
            parse_beta_version("v0.2.0-beta.1"),
            commit="a" * 40,
            repository="patrik-berg/SOLoRa",
        )


def test_beta_workflow_is_manual_and_prerelease_only() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/beta-release.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "confirm_prerelease:" in workflow
    assert 'test "$RELEASE_REF" = "refs/heads/main"' in workflow
    assert "--prerelease" in workflow
    assert "\n  push:" not in workflow
    assert "\n  schedule:" not in workflow


def _write(root: Path, relative: str, content: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
