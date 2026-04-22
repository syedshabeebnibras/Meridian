"""Redis-backed session store — prod.

Uses a Redis list per session_id with a 1-hour TTL refreshed on append.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from meridian_contracts import ConversationTurn


@dataclass
class RedisSessionStore:
    redis_client: object  # redis.Redis; left untyped to avoid a hard dep in tests
    ttl_seconds: int = 3600
    prefix: str = "meridian:session:"

    def _key(self, session_id: str) -> str:
        return f"{self.prefix}{session_id}"

    def get(self, session_id: str) -> list[ConversationTurn]:
        raw: list[bytes] = self.redis_client.lrange(self._key(session_id), 0, -1)  # type: ignore[attr-defined]
        turns: list[ConversationTurn] = []
        for item in raw:
            payload = json.loads(item.decode("utf-8") if isinstance(item, bytes) else item)
            turns.append(ConversationTurn.model_validate(payload))
        return turns

    def append(self, session_id: str, turn: ConversationTurn) -> None:
        key = self._key(session_id)
        payload = turn.model_dump_json()
        self.redis_client.rpush(key, payload)  # type: ignore[attr-defined]
        self.redis_client.expire(key, self.ttl_seconds)  # type: ignore[attr-defined]

    def clear(self, session_id: str) -> None:
        self.redis_client.delete(self._key(session_id))  # type: ignore[attr-defined]
