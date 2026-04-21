"""Regex-based PII detector — always-on baseline.

Real-world PII detection in production should use Presidio (Section 9
failure mode 7). This regex guardrail catches the obvious patterns
(emails, US SSN-like strings, US phone numbers, credit-card-like sequences)
so Meridian never ships with no PII defense. A Presidio HTTP client can
stack in front of or behind this one via the GuardrailPipeline.

Decision policy:
  - input:  REDACT (replace with placeholders so the model never sees raw PII)
  - output: BLOCK   (if the model produced PII that was never in input, that's a leak)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from meridian_guardrails.interfaces import GuardrailDecision, GuardrailOutcome

_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # US SSN with explicit delimiters — not bare 9-digit numbers.
    "SSN": re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"),
    # Credit-card-like (13-19 digit sequences with optional spaces/dashes).
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    # US phone — (555) 555-5555 / 555-555-5555 / 555.555.5555
    "PHONE": re.compile(r"\b(?:\(\d{3}\)\s?|\d{3}[-.\s])\d{3}[-.\s]\d{4}\b"),
}


def _detect(text: str) -> list[tuple[str, str]]:
    """Return a list of (entity_type, matched_substring)."""
    findings: list[tuple[str, str]] = []
    for entity, pattern in _PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append((entity, match.group(0)))
    return findings


def _redact(text: str) -> tuple[str, list[str]]:
    """Replace every match with <ENTITY_TYPE> placeholders."""
    redacted = text
    found_types: list[str] = []
    for entity, pattern in _PATTERNS.items():
        new, count = pattern.subn(f"<{entity}>", redacted)
        if count > 0:
            redacted = new
            found_types.extend([entity] * count)
    return redacted, found_types


@dataclass
class RegexPIIInputGuardrail:
    """Redacts PII from user input before it reaches the model."""

    name: str = "regex_pii_input"

    def check(self, text: str) -> GuardrailOutcome:
        redacted, found = _redact(text)
        if not found:
            return GuardrailOutcome(decision=GuardrailDecision.PASS, reason="no PII detected")
        return GuardrailOutcome(
            decision=GuardrailDecision.REDACT,
            reason=f"redacted {len(found)} PII spans",
            redacted_content=redacted,
            metadata={"entities": ",".join(sorted(set(found)))},
        )


@dataclass
class RegexPIIOutputGuardrail:
    """Blocks responses that contain PII the input didn't.

    The `context` must include an ``input_text`` key so we can tell whether
    any detected PII was already present upstream (e.g. the user pasted
    their own email into the query) or was fabricated by the model.
    """

    name: str = "regex_pii_output"

    def check(self, text: str, *, context: dict[str, str]) -> GuardrailOutcome:
        findings = _detect(text)
        if not findings:
            return GuardrailOutcome(decision=GuardrailDecision.PASS, reason="no PII in output")
        original_input = context.get("input_text", "")
        input_findings = {match for _, match in _detect(original_input)}
        leaked = [match for _, match in findings if match not in input_findings]
        if leaked:
            return GuardrailOutcome(
                decision=GuardrailDecision.BLOCK,
                reason=f"output contains PII not present in input: {len(leaked)} spans",
                metadata={"leaked_count": str(len(leaked))},
            )
        # PII appeared but matches input PII — pass through with a note.
        return GuardrailOutcome(
            decision=GuardrailDecision.PASS,
            reason="PII in output but all present in input",
        )
