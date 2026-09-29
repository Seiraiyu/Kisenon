"""The only forks this server will ever touch: the ones it created."""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from mcp.server.mcpserver.exceptions import ToolError

from kisenon_mcp import keon


@dataclass(slots=True)
class Fork:
    id: str
    name: str | None
    url: str
    created_at: float
    expires_at: float

    def public(self) -> dict:
        iso = lambda t: datetime.fromtimestamp(t, UTC).isoformat(timespec="seconds")  # noqa: E731
        return {"fork_id": self.id, "name": self.name,
                "created_at": iso(self.created_at), "expires_at": iso(self.expires_at)}


class UnknownFork(ToolError):
    """Raised as a ToolError so the model sees the message."""


class Registry:
    def __init__(self, *, project: str | None, ttl_s: int, clock=time.time):
        self.project, self.ttl_s, self.clock = project, ttl_s, clock
        self._forks: dict[str, Fork] = {}
        self._lock = threading.Lock()  # sync MCP tools run on worker threads

    def create(self, name: str | None = None) -> Fork:
        sandbox_id, url = keon.sandbox_create(project=self.project, ttl_s=self.ttl_s)
        now = self.clock()
        fork = Fork(sandbox_id, name, url, now, now + self.ttl_s)
        with self._lock:
            self._forks[fork.id] = fork
        return fork

    def get(self, fork_id: str) -> Fork:
        with self._lock:
            fork = self._forks.get(fork_id)
        if fork is None:
            raise UnknownFork(f"unknown fork_id {fork_id!r}: only forks created by "
                              "fork_database in this session can be used. Call fork_database.")
        return fork

    def list(self) -> list[Fork]:
        with self._lock:
            return list(self._forks.values())

    def destroy(self, fork_id: str) -> None:
        self.get(fork_id)
        with self._lock:
            self._forks.pop(fork_id, None)
        keon.sandbox_discard(fork_id)

    def reap(self) -> list[str]:
        """Destroy forks past their TTL. Errors are logged, not raised: the server
        auto-discards them anyway (their wall-clock budget is the same TTL)."""
        now = self.clock()
        with self._lock:
            expired = [f.id for f in self._forks.values() if f.expires_at <= now]
            for fid in expired:
                self._forks.pop(fid)
        for fid in expired:
            _quiet_discard(fid)
        return expired

    def destroy_all(self) -> None:
        with self._lock:
            ids, self._forks = list(self._forks), {}
        for fid in ids:
            _quiet_discard(fid)


def _quiet_discard(fork_id: str) -> None:
    try:
        keon.sandbox_discard(fork_id)
    except keon.KeonError as e:
        sys.stderr.write(f"[discard failed: {fork_id} | run `keon sandbox discard {fork_id}` "
                         f"| error={e}]\n")
