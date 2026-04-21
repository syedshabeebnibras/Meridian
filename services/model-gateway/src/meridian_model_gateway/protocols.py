"""ModelClient Protocol — what the orchestrator/evaluator depends on.

Phase 2 has one real implementation (LiteLLMClient) and one testing stub
(meridian_evaluator.stub_client.StubModelClient). Any new implementation
must conform to this Protocol.
"""

from __future__ import annotations

from typing import Protocol

from meridian_contracts import ModelRequest, ModelResponse


class ModelClient(Protocol):
    def chat(self, request: ModelRequest) -> ModelResponse: ...
