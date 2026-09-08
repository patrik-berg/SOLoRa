"""OS-released locks protect a data profile across restarts and owner crashes."""

from pathlib import Path

from filelock import FileLock


def owner_lock(data: Path, owner: str) -> FileLock:
    # Keep lock in the persistent profile, not a configurable temporary directory.
    # Never unlink a lock inode: contenders must all lock the same file.
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    return FileLock(data / f"{owner}.lock", timeout=0)
