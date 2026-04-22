"""SessionStore Protocol."""

from __future__ import annotations

from typing import Protocol

from meridian_contracts import ConversationTurn


class SessionStore(Protocol):
    """Stores conversation history per session_id.

    The orchestrator consults the store at the start of a request to
    hydrate `conversation_history` when the UserRequest didn't include
    it inline, and appends new turns at the end.
    """

    def get(self, session_id: str) -> list[ConversationTurn]: ...

    def append(self, session_id: str, turn: ConversationTurn) -> None: ...

    def clear(self, session_id: str) -> None: ...
