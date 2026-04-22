"""In-memory session store — tests + single-process dev."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from meridian_contracts import ConversationTurn


@dataclass
class InMemorySessionStore:
    """Keeps conversation history in a process-local dict with a TTL check.

    This is not a replacement for Redis in prod — an OOM crash drops
    everything, and there's no cross-instance sharing. Phase 7 wires
    RedisSessionStore by default.
    """

    ttl_seconds: float = 3600.0  # 1 hour per Section 7
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(tz=UTC))
    _turns: dict[str, list[ConversationTurn]] = field(default_factory=lambda: defaultdict(list))
    _touched: dict[str, datetime] = field(default_factory=dict)

    def get(self, session_id: str) -> list[ConversationTurn]:
        self._evict_if_stale(session_id)
        return list(self._turns.get(session_id, []))

    def append(self, session_id: str, turn: ConversationTurn) -> None:
        self._evict_if_stale(session_id)
        self._turns[session_id].append(turn)
        self._touched[session_id] = self.clock()

    def clear(self, session_id: str) -> None:
        self._turns.pop(session_id, None)
        self._touched.pop(session_id, None)

    def _evict_if_stale(self, session_id: str) -> None:
        touched = self._touched.get(session_id)
        if touched is None:
            return
        if self.clock() - touched > timedelta(seconds=self.ttl_seconds):
            self.clear(session_id)
