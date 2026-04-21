"""Llama Guard 3 input guardrail — classifies prompts for injection / unsafe intent.

Expects an HTTP endpoint that accepts ``{"text": "..."}`` and returns
``{"unsafe": bool, "categories": [...], "score": float}``. Adjust
_build_request / _parse_response if the team picks a different serving
shape (HF Inference API, Ollama, TGI, etc.).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from meridian_guardrails.interfaces import GuardrailDecision, GuardrailOutcome


@dataclass(frozen=True)
class LlamaGuardConfig:
    base_url: str = "http://localhost:7100"
    api_key: str = ""
    timeout_s: float = 0.5  # Section 7 input-guardrail budget

    @classmethod
    def from_env(cls) -> LlamaGuardConfig:
        return cls(
            base_url=os.environ.get("LLAMA_GUARD_BASE_URL", "http://localhost:7100"),
            api_key=os.environ.get("LLAMA_GUARD_API_KEY", ""),
            timeout_s=float(os.environ.get("LLAMA_GUARD_TIMEOUT_S", "0.5")),
        )


@dataclass
class LlamaGuardInputGuardrail:
    config: LlamaGuardConfig = field(default_factory=LlamaGuardConfig.from_env)
    http: httpx.Client | None = None
    name: str = "llama_guard_input"
    block_threshold: float = 0.5

    def __post_init__(self) -> None:
        if self.http is None:
            headers = (
                {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}
            )
            self.http = httpx.Client(
                base_url=self.config.base_url,
                timeout=self.config.timeout_s,
                headers=headers,
            )

    def check(self, text: str) -> GuardrailOutcome:
        assert self.http is not None
        try:
            response = self.http.post("/classify", json={"text": text})
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        except httpx.HTTPError as exc:
            # Fail-open: a guardrail outage shouldn't block legitimate traffic.
            # A real deployment wires a secondary detector; Phase 5 just degrades.
            return GuardrailOutcome(
                decision=GuardrailDecision.PASS,
                reason=f"llama_guard unreachable: {exc}",
                metadata={"degraded": "true"},
            )

        unsafe = bool(data.get("unsafe", False))
        score = float(data.get("score", 0.0))
        categories = ",".join(data.get("categories", []) or [])
        if unsafe and score >= self.block_threshold:
            return GuardrailOutcome(
                decision=GuardrailDecision.BLOCK,
                reason="llama_guard flagged input as unsafe",
                score=score,
                metadata={"categories": categories},
            )
        return GuardrailOutcome(
            decision=GuardrailDecision.PASS,
            reason="llama_guard: safe",
            score=score,
            metadata={"categories": categories},
        )
