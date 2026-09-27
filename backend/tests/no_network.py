"""A pytest plugin that makes any outbound socket connection fail.

Used to prove the offline claims rather than assert them:

    python -m pytest backend/tests -q -p tests.no_network

The mock provider and replay mode must pass with this plugin loaded. Loopback is
left alone so the in-process test client still works.
"""

from __future__ import annotations

import socket

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex

LOCAL = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}


class NetworkBlocked(RuntimeError):
    pass


def _host_of(address) -> str:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return str(address)


def _guarded_connect(self, address):  # type: ignore[no-untyped-def]
    host = _host_of(address)
    if host not in LOCAL:
        raise NetworkBlocked(
            f"This test run forbids network access, but something tried to reach {host}."
        )
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):  # type: ignore[no-untyped-def]
    host = _host_of(address)
    if host not in LOCAL:
        raise NetworkBlocked(
            f"This test run forbids network access, but something tried to reach {host}."
        )
    return _real_connect_ex(self, address)


def pytest_configure(config) -> None:  # type: ignore[no-untyped-def]
    socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]


def pytest_unconfigure(config) -> None:  # type: ignore[no-untyped-def]
    socket.socket.connect = _real_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _real_connect_ex  # type: ignore[method-assign]
