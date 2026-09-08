"""Atomic, validated bootstrap configuration, usable without HTTP or a database."""

import ipaddress
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class RuntimeConfig:
    bind: str = "127.0.0.1"
    port: int = 8000
    start_minimized: bool = False
    mode: Literal["desktop", "server"] = "desktop"
    lan_confirmed: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        # IPv4 only for v1 bootstrap; do not implicitly enable IPv6 dual stack.
        address = ipaddress.IPv4Address(self.bind)
        if address.is_multicast or self.bind == "255.255.255.255":
            raise ValueError("Bind must be a local unicast or wildcard IPv4 address")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("Port must be an integer between 1 and 65535")
        if any(type(value) is not bool for value in (self.start_minimized, self.lan_confirmed)):
            raise ValueError("Startup and LAN preferences must be booleans")
        if self.mode not in ("desktop", "server") or type(self.schema_version) is not int:
            raise ValueError("Invalid runtime mode or schema version")
        if self.schema_version != 1:
            raise ValueError("Unsupported bootstrap schema; configuration was not changed")
        if not address.is_loopback and not self.lan_confirmed:
            raise ValueError("Confirm LAN exposure: this forum currently has no authentication")

    def urls(self, addresses: tuple[str, ...] = ()) -> tuple[str, ...]:
        hosts = ("127.0.0.1", *addresses) if self.bind == "0.0.0.0" else (self.bind,)
        return tuple(dict.fromkeys(f"http://{host}:{self.port}/" for host in hosts))


class ConfigStore:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "runtime.json"

    def load(self) -> RuntimeConfig:
        if not self.path.exists():
            return RuntimeConfig()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Expected an object")
            return RuntimeConfig(**value)
        except (ValueError, TypeError) as error:
            raise ValueError(f"Invalid bootstrap config ({self.path}): {error}") from error

    def save(self, config: RuntimeConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, name = tempfile.mkstemp(prefix=".runtime-", dir=self.path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(asdict(config), stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
