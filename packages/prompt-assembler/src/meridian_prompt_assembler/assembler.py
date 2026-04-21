"""Prompt assembly — template rendering + token budgeting + cache hints.

The assembler is the single point where a PromptTemplate (static, versioned)
and a runtime AssemblyContext (retrieved docs, history, query, etc.) combine
into an AssembledPrompt ready for the model gateway.

Truncation priority (Section 6, highest-priority kept first):
  1. System prompt         — never truncated
  2. Output schema         — never truncated when structured output required
  3. Few-shot examples     — truncated last-to-first
  4. Retrieved documents   — truncated lowest-relevance-first
  5. Conversation history  — truncated oldest-first
  6. User query            — never truncated

Cache layout (Section 6):
  Stable prefix   = system + schema + few-shot examples
  Volatile suffix = retrieved docs + history + query
"""

from __future__ import annotations

from typing import Literal

from jinja2 import Environment, StrictUndefined
from meridian_contracts import (
    ConversationTurn,
    PromptTemplate,
    RetrievedChunk,
)
from pydantic import BaseModel, ConfigDict, Field

from meridian_prompt_assembler.tokens import TokenCounter, TokenCounterProtocol


class FewShotExample(BaseModel):
    """Runtime few-shot example passed to the assembler."""

    model_config = ConfigDict(extra="forbid")

    input_query: str
    expected_output: str
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class AssemblyContext(BaseModel):
    """Runtime inputs the assembler stitches into the template."""

    model_config = ConfigDict(extra="forbid")

    user_query: str
    retrieved_docs: list[RetrievedChunk] = Field(default_factory=list)
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    few_shot_examples: list[FewShotExample] = Field(default_factory=list)
    system_vars: dict[str, str] = Field(default_factory=dict)


class AssembledMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str
    cache_breakpoint_after: bool = Field(
        default=False,
        description=(
            "Signal to the model gateway that provider-native cache_control "
            "should be inserted immediately after this message. Mapped to the "
            "template's cache_control.breakpoints configuration."
        ),
    )


class TruncationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: Literal["history", "retrieved_docs", "few_shot"]
    dropped_count: int = Field(ge=0)
    reason: str


class AssembledPrompt(BaseModel):
    """Output of the assembler. Consumed by the model gateway."""

    model_config = ConfigDict(extra="forbid")

    template_name: str
    template_version: int
    messages: list[AssembledMessage]
    token_counts: dict[str, int]
    total_tokens: int
    truncation_events: list[TruncationEvent] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Jinja environment
# ---------------------------------------------------------------------------
def _env() -> Environment:
    env = Environment(
        undefined=StrictUndefined,
        keep_trailing_newline=False,
        autoescape=False,  # prompts are not HTML
    )
    env.filters["last_n_turns"] = lambda turns, n: turns[-n:] if n else turns
    # Back-compat alias referenced in Section 6 examples.
    env.filters["last_4_turns"] = lambda turns: turns[-4:]
    return env


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------
class Assembler:
    """Render + budget + emit cache hints."""

    def __init__(self, counter: TokenCounterProtocol | None = None) -> None:
        self._counter = counter or TokenCounter()
        self._jinja = _env()

    def assemble(
        self,
        template: PromptTemplate,
        context: AssemblyContext,
    ) -> AssembledPrompt:
        """Produce the assembled prompt. Pure — no I/O."""

        truncations: list[TruncationEvent] = []

        # ---- 1. Apply token budgets BEFORE rendering ---------------------
        docs, docs_truncated = self._fit_retrieved_docs(
            context.retrieved_docs, template.token_budget.retrieval
        )
        if docs_truncated:
            truncations.append(
                TruncationEvent(
                    section="retrieved_docs",
                    dropped_count=docs_truncated,
                    reason=f"retrieval budget {template.token_budget.retrieval} tokens",
                )
            )

        history, history_truncated = self._fit_history(
            context.conversation_history, template.token_budget.history
        )
        if history_truncated:
            truncations.append(
                TruncationEvent(
                    section="history",
                    dropped_count=history_truncated,
                    reason=f"history budget {template.token_budget.history} tokens",
                )
            )

        few_shots, few_shot_truncated = self._fit_few_shots(
            context.few_shot_examples, template.token_budget.few_shot
        )
        if few_shot_truncated:
            truncations.append(
                TruncationEvent(
                    section="few_shot",
                    dropped_count=few_shot_truncated,
                    reason=f"few_shot budget {template.token_budget.few_shot} tokens",
                )
            )

        # ---- 2. Render the template --------------------------------------
        rendered = self._render(
            template=template,
            context=context,
            retrieved_docs=docs,
            conversation_history=history,
            few_shot_examples=few_shots,
        )

        # ---- 3. Split into system/user messages --------------------------
        messages = self._split_into_messages(rendered, template)

        # ---- 4. Count final tokens per section ---------------------------
        counts = {
            "system": sum(self._counter.count(m.content) for m in messages if m.role == "system"),
            "user": sum(self._counter.count(m.content) for m in messages if m.role == "user"),
            "assistant": sum(
                self._counter.count(m.content) for m in messages if m.role == "assistant"
            ),
        }
        total = sum(counts.values())

        return AssembledPrompt(
            template_name=template.name,
            template_version=template.version,
            messages=messages,
            token_counts=counts,
            total_tokens=total,
            truncation_events=truncations,
        )

    # ------------------------------------------------------------------
    # budgeting
    # ------------------------------------------------------------------
    def _fit_retrieved_docs(
        self, docs: list[RetrievedChunk], budget: int
    ) -> tuple[list[RetrievedChunk], int]:
        """Keep docs in the given order until budget is exhausted.

        RetrievedChunks arrive pre-ranked by the retrieval pipeline (relevance
        desc). Truncation drops from the tail.
        """
        if budget <= 0 or not docs:
            return [], len(docs)

        kept: list[RetrievedChunk] = []
        running = 0
        for doc in docs:
            chunk_tokens = self._counter.count(doc.content)
            if running + chunk_tokens > budget:
                break
            kept.append(doc)
            running += chunk_tokens
        return kept, len(docs) - len(kept)

    def _fit_history(
        self, history: list[ConversationTurn], budget: int
    ) -> tuple[list[ConversationTurn], int]:
        """Keep the newest turns until budget is exhausted (oldest truncated first)."""
        if budget <= 0 or not history:
            return [], len(history)

        kept: list[ConversationTurn] = []
        running = 0
        for turn in reversed(history):
            turn_tokens = self._counter.count(turn.content)
            if running + turn_tokens > budget:
                break
            kept.insert(0, turn)
            running += turn_tokens
        return kept, len(history) - len(kept)

    def _fit_few_shots(
        self, examples: list[FewShotExample], budget: int
    ) -> tuple[list[FewShotExample], int]:
        """Keep earliest few-shots until budget exhausted (last-to-first truncation)."""
        if budget <= 0 or not examples:
            return [], len(examples)

        kept: list[FewShotExample] = []
        running = 0
        for ex in examples:
            ex_tokens = self._counter.count(ex.input_query) + self._counter.count(
                ex.expected_output
            )
            if running + ex_tokens > budget:
                break
            kept.append(ex)
            running += ex_tokens
        return kept, len(examples) - len(kept)

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------
    def _render(
        self,
        *,
        template: PromptTemplate,
        context: AssemblyContext,
        retrieved_docs: list[RetrievedChunk],
        conversation_history: list[ConversationTurn],
        few_shot_examples: list[FewShotExample],
    ) -> str:
        jinja_tmpl = self._jinja.from_string(template.template)
        return jinja_tmpl.render(
            user_query=context.user_query,
            retrieved_docs=retrieved_docs,
            conversation_history=conversation_history,
            few_shot_examples=few_shot_examples,
            **context.system_vars,
        )

    # ------------------------------------------------------------------
    # message splitting
    # ------------------------------------------------------------------
    def _split_into_messages(
        self, rendered: str, template: PromptTemplate
    ) -> list[AssembledMessage]:
        """Split a rendered template string into system + user messages.

        Convention: templates use [SYSTEM], [USER], and [ASSISTANT] markers at
        the start of each section. Text before the first marker is ignored.
        Cache breakpoints from template.cache_control.breakpoints map onto
        message boundaries: `after_system` ⇒ breakpoint after the system
        message; `after_few_shot` ⇒ breakpoint at the end of the stable
        prefix (modelled as the system message for Phase 2 simplicity).
        """
        marker_map = {"[SYSTEM]": "system", "[USER]": "user", "[ASSISTANT]": "assistant"}
        sections: list[tuple[str, str]] = []  # (role, content)
        current_role: str | None = None
        buffer: list[str] = []

        for line in rendered.splitlines():
            stripped = line.strip()
            matched_marker = next((m for m in marker_map if stripped.startswith(m)), None)
            if matched_marker is not None:
                if current_role is not None:
                    sections.append((current_role, "\n".join(buffer).strip()))
                current_role = marker_map[matched_marker]
                tail = stripped[len(matched_marker) :].lstrip()
                buffer = [tail] if tail else []
            else:
                buffer.append(line)
        if current_role is not None:
            sections.append((current_role, "\n".join(buffer).strip()))

        breakpoints = set(template.cache_control.breakpoints)
        messages: list[AssembledMessage] = []
        for role, content in sections:
            breakpoint_after = False
            if role == "system" and (
                "after_system" in breakpoints or "after_few_shot" in breakpoints
            ):
                breakpoint_after = True
            if not content:
                continue
            messages.append(
                AssembledMessage(
                    role=role,
                    content=content,
                    cache_breakpoint_after=breakpoint_after,
                )
            )
        return messages
