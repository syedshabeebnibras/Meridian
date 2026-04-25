"""Per-request workspace contextvar.

The retrieval client interface ``RetrievalClient.retrieve(query, *, top_k)``
is workspace-agnostic by design — it predates the tenant model. Rather
than churning every implementation, we thread workspace_id through the
request lifecycle via a contextvar that the API layer sets and the local
retrieval client reads.

ContextVar (not threading.local) so this works correctly under FastAPI's
async request handling: each task gets its own copy.
"""

from __future__ import annotations

from contextvars import ContextVar

WORKSPACE_ID: ContextVar[str | None] = ContextVar("meridian_workspace_id", default=None)
