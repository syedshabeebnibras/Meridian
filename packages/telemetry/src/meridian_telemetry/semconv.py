"""OpenTelemetry GenAI semantic conventions + Meridian-specific attributes.

Keys mirror Section 8 "Telemetry event contract" — any field added there must
be mirrored here so spans stay queryable.
"""

from typing import Final


class GenAIAttr:
    """OTel GenAI semantic convention attribute keys."""

    SYSTEM: Final[str] = "gen_ai.system"
    REQUEST_MODEL: Final[str] = "gen_ai.request.model"
    RESPONSE_MODEL: Final[str] = "gen_ai.response.model"
    INPUT_TOKENS: Final[str] = "gen_ai.usage.input_tokens"
    OUTPUT_TOKENS: Final[str] = "gen_ai.usage.output_tokens"
    CACHE_READ_TOKENS: Final[str] = "gen_ai.usage.cache_read_tokens"
    FINISH_REASON: Final[str] = "gen_ai.response.finish_reason"


class MeridianAttr:
    """Meridian-specific span attributes."""

    REQUEST_ID: Final[str] = "meridian.request_id"
    PROMPT_VERSION: Final[str] = "meridian.prompt_version"
    MODEL_TIER: Final[str] = "meridian.model_tier"
    INTENT: Final[str] = "meridian.intent"
    COST_USD: Final[str] = "meridian.cost_usd"
    CACHE_HIT: Final[str] = "meridian.cache_hit"
    PROVIDER_ATTEMPT: Final[str] = "meridian.provider_attempt"
    RETRIEVAL_CHUNKS_USED: Final[str] = "meridian.retrieval_chunks_used"
