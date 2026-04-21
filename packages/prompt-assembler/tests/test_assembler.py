"""Unit tests for the prompt assembler — rendering, budgeting, cache hints."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from jinja2 import UndefinedError
from meridian_contracts import (
    ActivationInfo,
    ActivationStatus,
    CacheControl,
    ConversationTurn,
    ModelTier,
    PromptTemplate,
    RetrievedChunk,
    TokenBudget,
)
from meridian_prompt_assembler import (
    AssembledPrompt,
    Assembler,
    AssemblyContext,
    FewShotExample,
    TokenCounterProtocol,
)


class FakeCounter:
    """Word-count tokenizer — deterministic, good enough for tests."""

    def count(self, text: str) -> int:
        return len(text.split())


def _template(
    *,
    body: str,
    budget: TokenBudget | None = None,
    breakpoints: list[str] | None = None,
) -> PromptTemplate:
    return PromptTemplate(
        name="test_template",
        version=1,
        model_tier=ModelTier.MID,
        min_model="claude-sonnet-4-6",
        template=body,
        parameters=["user_query"],
        schema_ref="test_v1",
        few_shot_dataset=None,
        token_budget=budget
        or TokenBudget(
            system=100, few_shot=100, retrieval=100, history=100, query=50, total_max=1000
        ),
        cache_control=CacheControl(breakpoints=breakpoints or [], prefix_stable=True),
        activation=ActivationInfo(
            environment="test",
            status=ActivationStatus.DRAFT,
            canary_percentage=0,
            activated_at=datetime.now(tz=UTC),
            activated_by="t@t.com",
        ),
    )


def _counter() -> TokenCounterProtocol:
    return FakeCounter()


def test_simple_rendering_produces_system_and_user_messages() -> None:
    tmpl = _template(
        body=("[SYSTEM] You are Meridian, helpful to {{ company_name }}.\n[USER] {{ user_query }}"),
    )
    ctx = AssemblyContext(
        user_query="What time is it?",
        system_vars={"company_name": "Acme"},
    )
    prompt = Assembler(counter=_counter()).assemble(tmpl, ctx)

    assert [m.role for m in prompt.messages] == ["system", "user"]
    assert "Meridian" in prompt.messages[0].content
    assert "Acme" in prompt.messages[0].content
    assert prompt.messages[1].content == "What time is it?"
    assert prompt.template_name == "test_template"
    assert prompt.template_version == 1
    assert prompt.total_tokens > 0


def test_retrieval_truncation_drops_lowest_relevance() -> None:
    # budget only fits two of three docs (each doc is 5 words).
    budget = TokenBudget(system=50, few_shot=0, retrieval=10, history=0, query=20, total_max=200)
    tmpl = _template(
        body="[SYSTEM] s\n[USER] q",
        budget=budget,
    )
    docs = [
        RetrievedChunk(
            index=i,
            chunk_id=f"c{i}",
            source_title=f"t{i}",
            source_url="https://example.com/",
            content="word " * 5,
            relevance_score=1.0 - (i * 0.1),
        )
        for i in range(1, 4)
    ]
    prompt = Assembler(counter=_counter()).assemble(
        tmpl, AssemblyContext(user_query="q", retrieved_docs=docs)
    )
    trunc = [e for e in prompt.truncation_events if e.section == "retrieved_docs"]
    assert len(trunc) == 1
    assert trunc[0].dropped_count == 1


def test_history_truncation_drops_oldest_first() -> None:
    budget = TokenBudget(system=50, few_shot=0, retrieval=0, history=4, query=20, total_max=200)
    tmpl = _template(body="[SYSTEM] s\n[USER] q", budget=budget)
    history = [
        ConversationTurn(
            role="user" if i % 2 == 0 else "assistant",
            content=f"turn {i} one two three",  # 5 words
            timestamp=datetime.now(tz=UTC),
        )
        for i in range(3)
    ]
    prompt = Assembler(counter=_counter()).assemble(
        tmpl, AssemblyContext(user_query="q", conversation_history=history)
    )
    trunc = [e for e in prompt.truncation_events if e.section == "history"]
    assert trunc and trunc[0].dropped_count == 3
    # All three dropped because even the newest doesn't fit (5 > 4).


def test_history_retains_newest_turns_when_they_fit() -> None:
    # 10-token budget, each turn is 3 tokens, so 3 turns fit.
    budget = TokenBudget(system=50, few_shot=0, retrieval=0, history=10, query=20, total_max=200)
    tmpl = _template(body="[SYSTEM] s\n[USER] q", budget=budget)
    history = [
        ConversationTurn(
            role="user",
            content=f"old turn {i}",  # 3 words
            timestamp=datetime.now(tz=UTC),
        )
        for i in range(5)
    ]
    prompt = Assembler(counter=_counter()).assemble(
        tmpl, AssemblyContext(user_query="q", conversation_history=history)
    )
    trunc = [e for e in prompt.truncation_events if e.section == "history"]
    # 3 turns (9 tokens) fit; 2 dropped.
    assert trunc and trunc[0].dropped_count == 2


def test_few_shot_truncation_drops_last_first() -> None:
    budget = TokenBudget(system=50, few_shot=6, retrieval=0, history=0, query=20, total_max=200)
    tmpl = _template(body="[SYSTEM] s\n[USER] q", budget=budget)
    # Each example is 4 tokens (2 in/2 out). Budget fits 1 example (4 tokens <= 6).
    examples = [FewShotExample(input_query=f"q {i}", expected_output=f"a {i}") for i in range(3)]
    prompt = Assembler(counter=_counter()).assemble(
        tmpl,
        AssemblyContext(user_query="q", few_shot_examples=examples),
    )
    trunc = [e for e in prompt.truncation_events if e.section == "few_shot"]
    assert trunc and trunc[0].dropped_count == 2  # examples 1 and 2 dropped


def test_cache_breakpoint_marked_after_system() -> None:
    tmpl = _template(
        body="[SYSTEM] constant header\n[USER] {{ user_query }}",
        breakpoints=["after_system"],
    )
    prompt = Assembler(counter=_counter()).assemble(tmpl, AssemblyContext(user_query="q"))
    system_msg = next(m for m in prompt.messages if m.role == "system")
    user_msg = next(m for m in prompt.messages if m.role == "user")
    assert system_msg.cache_breakpoint_after is True
    assert user_msg.cache_breakpoint_after is False


def test_no_cache_breakpoints_when_template_opts_out() -> None:
    tmpl = _template(
        body="[SYSTEM] s\n[USER] {{ user_query }}",
        breakpoints=[],
    )
    prompt = Assembler(counter=_counter()).assemble(tmpl, AssemblyContext(user_query="q"))
    assert all(not m.cache_breakpoint_after for m in prompt.messages)


def test_retrieved_docs_render_in_template() -> None:
    body = (
        "[SYSTEM] You are an assistant.\n"
        "[USER] {% for doc in retrieved_docs %}[DOC-{{ doc.index }}] "
        "{{ doc.source_title }}\n{{ doc.content }}\n{% endfor %}"
        "Question: {{ user_query }}"
    )
    tmpl = _template(body=body)
    docs = [
        RetrievedChunk(
            index=1,
            chunk_id="c1",
            source_title="Runbook",
            source_url="https://example.com/r",
            content="procedure steps",
            relevance_score=0.9,
        )
    ]
    prompt = Assembler(counter=_counter()).assemble(
        tmpl, AssemblyContext(user_query="What do I do?", retrieved_docs=docs)
    )
    user_content = next(m for m in prompt.messages if m.role == "user").content
    assert "[DOC-1]" in user_content
    assert "Runbook" in user_content
    assert "procedure steps" in user_content
    assert "What do I do?" in user_content


def test_assembled_prompt_is_contract_compliant() -> None:
    """AssembledPrompt round-trips through Pydantic JSON — confirms it's a stable contract."""
    tmpl = _template(body="[SYSTEM] s\n[USER] {{ user_query }}")
    prompt = Assembler(counter=_counter()).assemble(tmpl, AssemblyContext(user_query="hi"))
    dumped = prompt.model_dump_json()
    AssembledPrompt.model_validate_json(dumped)


def test_missing_system_var_raises() -> None:
    tmpl = _template(body="[SYSTEM] {{ company_name }}\n[USER] {{ user_query }}")
    with pytest.raises(UndefinedError):
        Assembler(counter=_counter()).assemble(tmpl, AssemblyContext(user_query="q"))
