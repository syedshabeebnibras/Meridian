"""InMemorySessionStore tests — TTL eviction, isolation, append+get."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from meridian_contracts import ConversationTurn
from meridian_session_store import InMemorySessionStore


def _turn(role: str, content: str, when: datetime | None = None) -> ConversationTurn:
    return ConversationTurn(
        role=role,  # type: ignore[arg-type]
        content=content,
        timestamp=when or datetime.now(tz=UTC),
    )


def test_append_and_get_round_trip() -> None:
    store = InMemorySessionStore()
    store.append("s1", _turn("user", "hi"))
    store.append("s1", _turn("assistant", "hello"))
    turns = store.get("s1")
    assert [t.content for t in turns] == ["hi", "hello"]


def test_sessions_are_isolated() -> None:
    store = InMemorySessionStore()
    store.append("s1", _turn("user", "hi"))
    store.append("s2", _turn("user", "bye"))
    assert [t.content for t in store.get("s1")] == ["hi"]
    assert [t.content for t in store.get("s2")] == ["bye"]


def test_ttl_evicts_stale_session() -> None:
    now = datetime.now(tz=UTC)
    current = now

    def clock() -> datetime:
        return current

    store = InMemorySessionStore(ttl_seconds=10.0, clock=clock)
    store.append("s1", _turn("user", "old"))
    assert [t.content for t in store.get("s1")] == ["old"]
    # Fast-forward past the TTL.
    current = now + timedelta(seconds=20)
    assert store.get("s1") == []


def test_clear_removes_session() -> None:
    store = InMemorySessionStore()
    store.append("s1", _turn("user", "hi"))
    store.clear("s1")
    assert store.get("s1") == []


def test_get_empty_session_returns_empty_list() -> None:
    store = InMemorySessionStore()
    assert store.get("never-used") == []
