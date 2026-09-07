"""Validate, version, and package a SOLoRa beta release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

BASE_VERSION_PATTERN = re.compile(r"0\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
BETA_VERSION_PATTERN = re.compile(
    r"v(?P<base>0\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))-beta\.(?P<number>[1-9]\d*)"
)
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class ReleaseError(ValueError):
    """Raised when release input or build output is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class BetaVersion:
    """One public SemVer beta tag and its PEP 440 equivalent."""

    tag: str
    base: str
    number: int

    @property
    def python(self) -> str:
        return f"{self.base}b{self.number}"


def parse_base_version(value: str) -> str:
    """Validate the stable-looking base used to number prereleases."""
    if BASE_VERSION_PATTERN.fullmatch(value) is None:
        raise ReleaseError("Base version must match 0.x.x without leading zeroes")
    return value


def parse_beta_version(value: str) -> BetaVersion:
    """Parse the only tag shape the beta workflow may publish."""
    match = BETA_VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise ReleaseError("Beta version must match v0.x.x-beta.N")
    return BetaVersion(value, match.group("base"), int(match.group("number")))


def next_beta_version(base: str, tags: Iterable[str]) -> BetaVersion:
    """Return the next beta number for a base, ignoring unrelated tags."""
    normalized_base = parse_base_version(base)
    numbers = []
    for tag in tags:
        match = BETA_VERSION_PATTERN.fullmatch(tag.strip())
        if match is not None and match.group("base") == normalized_base:
            numbers.append(int(match.group("number")))
    number = max(numbers, default=0) + 1
    return parse_beta_version(f"v{normalized_base}-beta.{number}")


def repository_tags(root: Path) -> list[str]:
    """Read tags from the checked-out repository."""
    result = subprocess.run(
        ["git", "tag", "--list"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def stage_version(root: Path, version: BetaVersion) -> None:
    """Stage consistent build metadata in the disposable Actions checkout."""
    pyproject = root / "pyproject.toml"
    package_init = root / "backend" / "src" / "solora" / "__init__.py"
    package_json = root / "frontend" / "package.json"

    _replace_once(
        pyproject,
        r'(?m)^version = "[^"]+"$',
        f'version = "{version.python}"',
    )
    _replace_once(
        package_init,
        r'(?m)^__version__ = "[^"]+"$',
        f'__version__ = "{version.python}"',
    )
    package_data = json.loads(package_json.read_text(encoding="utf-8"))
    package_data["version"] = version.tag.removeprefix("v")
    package_json.write_text(
        json.dumps(package_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_bundle(
    root: Path,
    output_dir: Path,
    version: BetaVersion,
    *,
    commit: str,
    repository: str,
) -> tuple[Path, Path]:
    """Create one portable bundle and its machine-readable update manifest."""
    if COMMIT_PATTERN.fullmatch(commit) is None:
        raise ReleaseError("Commit must be a full lowercase SHA-1")
    if not repository or "/" not in repository:
        raise ReleaseError("Repository must use owner/name form")

    wheel = root / "dist" / f"solora-{version.python}-py3-none-any.whl"
    source = root / "dist" / f"solora-{version.python}.tar.gz"
    frontend = root / "frontend" / "dist"
    required = [wheel, source, frontend / "index.html"]
    missing = [str(path.relative_to(root)) for path in required if not path.exists()]
    if missing:
        raise ReleaseError(f"Missing build output: {', '.join(missing)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = output_dir / f"solora-{version.tag}-portable.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _write_path(archive, wheel, f"backend/{wheel.name}")
        _write_path(archive, source, f"backend/{source.name}")
        _write_path(archive, root / "backend" / "alembic.ini", "backend/alembic.ini")
        for path in _release_files(root / "backend" / "migrations"):
            _write_path(archive, path, path.relative_to(root).as_posix())
        for path in _release_files(frontend):
            _write_path(archive, path, path.relative_to(root).as_posix())
        for name in ("README.md", "ARCHITECTURE.md", "PROTOCOL.md"):
            _write_path(archive, root / name, name)
        _write_text(archive, "VERSION", f"{version.tag}\n")
        _write_text(archive, "manage.py", _launcher_source())
        _write_text(
            archive,
            "BETA_README.md",
            _beta_readme(version, wheel.name, repository),
        )

    digest = _sha256(bundle)
    manifest = output_dir / f"solora-{version.tag}-update.json"
    manifest_data = {
        "schema_version": 1,
        "channel": "beta",
        "version": version.tag,
        "python_version": version.python,
        "commit": commit,
        "repository": repository,
        "stable": False,
        "assets": [
            {
                "kind": "portable-python",
                "name": bundle.name,
                "sha256": digest,
                "size": bundle.stat().st_size,
            }
        ],
    }
    manifest.write_text(
        json.dumps(manifest_data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return bundle, manifest


def _replace_once(path: Path, pattern: str, replacement: str) -> None:
    original = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, original, count=1)
    if count != 1:
        raise ReleaseError(f"Could not identify exactly one version in {path}")
    path.write_text(updated, encoding="utf-8")


def _release_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )


def _write_path(archive: zipfile.ZipFile, source: Path, destination: str) -> None:
    _write_bytes(archive, destination, source.read_bytes())


def _write_text(archive: zipfile.ZipFile, destination: str, content: str) -> None:
    _write_bytes(archive, destination, content.encode("utf-8"))


def _write_bytes(archive: zipfile.ZipFile, destination: str, content: bytes) -> None:
    info = zipfile.ZipInfo(destination, ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, content)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _launcher_source() -> str:
    return '''"""Run the unpacked SOLoRa beta bundle."""

from pathlib import Path

from alembic import command
from alembic.config import Config
import uvicorn

from solora.app import create_app

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATABASE_URL = f"sqlite:///{DATA / 'solora.db'}"


def main() -> None:
    DATA.mkdir(exist_ok=True)
    config = Config(ROOT / "backend" / "alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    app = create_app(
        database_url=DATABASE_URL,
        frontend_path=ROOT / "frontend" / "dist",
    )
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
'''


def _beta_readme(version: BetaVersion, wheel_name: str, repository: str) -> str:
    return f"""# SOLoRa {version.tag}

This is a prerelease test bundle, not a native signed installer. It works on macOS,
Linux, and Windows with Python 3.12. Do not treat it as a Stable release.

1. Create and activate a virtual environment: `python3.12 -m venv .venv`.
2. Install `backend/{wheel_name}` with that environment's pip.
3. Run `python manage.py` from this directory.
4. Open http://127.0.0.1:8000/ and stop with Ctrl+C.

The launcher migrates and stores the local database under `data/`. Back up that
directory before replacing a beta. Verify release provenance with GitHub CLI:
`gh attestation verify <bundle.zip> --repo {repository}`.
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    next_parser = subparsers.add_parser("next", help="print the next beta tag")
    next_parser.add_argument("--base", required=True)
    next_parser.add_argument("--root", type=Path, default=Path.cwd())

    stage_parser = subparsers.add_parser("stage", help="stage build-only version metadata")
    stage_parser.add_argument("--version", required=True)
    stage_parser.add_argument("--root", type=Path, default=Path.cwd())

    bundle_parser = subparsers.add_parser("bundle", help="create release assets")
    bundle_parser.add_argument("--version", required=True)
    bundle_parser.add_argument("--commit", required=True)
    bundle_parser.add_argument("--repository", required=True)
    bundle_parser.add_argument("--root", type=Path, default=Path.cwd())
    bundle_parser.add_argument("--output-dir", type=Path, default=Path("release"))
    return parser


def main() -> None:
    args = _parser().parse_args()
    root = args.root.resolve()
    if args.command == "next":
        print(next_beta_version(args.base, repository_tags(root)).tag)
    elif args.command == "stage":
        stage_version(root, parse_beta_version(args.version))
    else:
        bundle, manifest = build_bundle(
            root,
            args.output_dir.resolve(),
            parse_beta_version(args.version),
            commit=args.commit,
            repository=args.repository,
        )
        print(bundle)
        print(manifest)


if __name__ == "__main__":
    main()
