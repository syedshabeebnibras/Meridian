"""Patronus Lynx — faithfulness checker.

Expects an API that accepts ``{"answer": "...", "context": "..."}`` and
returns ``{"faithful": bool, "score": float, "reason": "..."}``. Adjust
_build_request / _parse_response if the team picks the self-hosted Lynx
model (HF) or a different vendor API shape.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from meridian_guardrails.interfaces import GuardrailDecision, GuardrailOutcome


@dataclass(frozen=True)
class PatronusConfig:
    base_url: str = "https://api.patronus.ai"
    api_key: str = ""
    timeout_s: float = 1.0  # output-guardrail budget

    @classmethod
    def from_env(cls) -> PatronusConfig:
        return cls(
            base_url=os.environ.get("PATRONUS_BASE_URL", "https://api.patronus.ai"),
            api_key=os.environ.get("PATRONUS_API_KEY", ""),
            timeout_s=float(os.environ.get("PATRONUS_TIMEOUT_S", "1.0")),
        )


@dataclass
class PatronusLynxOutputGuardrail:
    config: PatronusConfig = field(default_factory=PatronusConfig.from_env)
    http: httpx.Client | None = None
    name: str = "patronus_lynx"
    min_score: float = 0.8  # Section 10 launch gate aligns with 0.85 overall

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

    def check(self, text: str, *, context: dict[str, str]) -> GuardrailOutcome:
        assert self.http is not None
        retrieved = context.get("retrieved_docs_text", "")
        try:
            response = self.http.post(
                "/v1/lynx/check",
                json={"answer": text, "context": retrieved},
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        except httpx.HTTPError as exc:
            return GuardrailOutcome(
                decision=GuardrailDecision.PASS,
                reason=f"patronus unreachable: {exc}",
                metadata={"degraded": "true"},
            )

        score = float(data.get("score", 0.0))
        faithful = bool(data.get("faithful", score >= self.min_score))
        if faithful and score >= self.min_score:
            return GuardrailOutcome(
                decision=GuardrailDecision.PASS,
                reason="patronus: faithful",
                score=score,
            )
        return GuardrailOutcome(
            decision=GuardrailDecision.BLOCK,
            reason=f"patronus: faithfulness {score:.2f} < {self.min_score:.2f}",
            score=score,
            metadata={"patronus_reason": str(data.get("reason", ""))},
        )
