"""Feedback storage backends for /v1/feedback.

Two implementations:
  - InMemoryFeedbackStore — single-process, used for tests and dev.
  - PostgresFeedbackStore  — durable, append-only writes to ``request_feedback``.

The Protocol lives here so api.py and wiring.py can both import without
introducing a circular dependency.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from meridian_orchestrator.api import FeedbackRequest


class FeedbackStore(Protocol):
    """Anything that can persist a feedback record."""

    def record(self, feedback: FeedbackRequest) -> None: ...


@dataclass
class InMemoryFeedbackStore:
    entries: list[FeedbackRequest] = field(default_factory=list)

    def record(self, feedback: FeedbackRequest) -> None:
        self.entries.append(feedback)


@dataclass
class PostgresFeedbackStore:
    """Append-only writer for ``request_feedback``.

    We open a fresh session per write so a flapping connection on one
    request doesn't poison subsequent ones — feedback is low volume.
    """

    session_factory: Callable[[], Session] | sessionmaker[Session]

    def record(self, feedback: FeedbackRequest) -> None:
        # Local import — keeps the orchestrator package importable in test
        # environments that don't have meridian_db installed.
        from meridian_db.models import RequestFeedbackRow

        with self.session_factory() as session:
            session.add(
                RequestFeedbackRow(
                    id=uuid.uuid4(),
                    request_id=feedback.request_id,
                    user_id=feedback.user_id,
                    verdict=feedback.verdict,
                    comment=feedback.comment,
                )
            )
            session.commit()
