"""StubModelClient — scripted responses for offline regression runs.

The regressor constructs a StubModelClient from the dataset's ``stub_response``
fields so CI can exercise the full assembler → client → scorer flow without
touching the network.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from meridian_contracts import ModelRequest, ModelResponse, ModelUsage


class StubModelClient:
    """ModelClient implementation that returns pre-registered responses.

    Matching happens by ``(model, first-user-message)`` so the same template
    serves across tests. A custom ``matcher`` can override this for edge-case
    tests.
    """

    def __init__(
        self,
        matcher: Callable[[ModelRequest], ModelResponse] | None = None,
    ) -> None:
        self._responses: dict[tuple[str, str], ModelResponse] = {}
        self._matcher = matcher

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(
        self,
        *,
        model: str,
        user_content_fragment: str,
        content: dict[str, object] | str,
        latency_ms: int = 50,
    ) -> None:
        """Register a canned response. `user_content_fragment` can be any
        substring of the user message; the first match wins."""
        key = (model, user_content_fragment)
        self._responses[key] = ModelResponse(
            id=f"stub_{uuid.uuid4().hex[:8]}",
            model=model,
            content=content,
            usage=ModelUsage(input_tokens=0, output_tokens=0),
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------
    # ModelClient protocol
    # ------------------------------------------------------------------
    def chat(self, request: ModelRequest) -> ModelResponse:
        if self._matcher is not None:
            return self._matcher(request)

        user_content = next((m.content for m in request.messages if m.role == "user"), "")
        for (model, fragment), response in self._responses.items():
            if model == request.model and fragment in user_content:
                return response
        raise KeyError(
            f"no stub registered for model={request.model!r} "
            f"with a user fragment matching the request"
        )
