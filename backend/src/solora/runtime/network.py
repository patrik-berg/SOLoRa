"""Local interface discovery and listener validation; never sends radio traffic."""

import socket

import psutil

from solora.runtime.settings import RuntimeConfig


def interfaces() -> dict[str, str]:
    result = {"Localhost — 127.0.0.1": "127.0.0.1", "All IPv4 interfaces": "0.0.0.0"}
    for name, entries in psutil.net_if_addrs().items():
        for entry in entries:
            if entry.family == socket.AF_INET and entry.address != "127.0.0.1":
                result[f"{name} — {entry.address}"] = entry.address
    return result


def bind_socket(config: RuntimeConfig) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((config.bind, config.port))
        listener.listen(128)
        listener.setblocking(False)
    except OSError as error:
        listener.close()
        raise OSError(
            f"Cannot listen on {config.bind}:{config.port}: {error.strerror}. "
            "Check for an occupied port, unavailable interface, or missing permission."
        ) from error
    return listener
