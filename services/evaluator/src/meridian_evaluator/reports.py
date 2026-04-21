"""Markdown report renderer for RegressionResult."""

from __future__ import annotations

from meridian_evaluator.regressor import RegressionResult


def render_markdown_report(result: RegressionResult) -> str:
    lines: list[str] = []
    lines.append(f"# Regression — {result.dataset_name}\n")
    lines.append(f"- Prompt: `{result.prompt_name}` v{result.prompt_version}")
    lines.append(f"- Total: {result.total}")
    lines.append(f"- Passed: {result.passed} / {result.total}")
    lines.append(f"- Pass rate: **{result.pass_rate:.2%}**")
    lines.append(f"- Mean score: **{result.mean_score:.3f}**\n")
    lines.append("## Per-example\n")
    lines.append("| # | Pass | Score | Input |")
    lines.append("|---|---|---|---|")
    for i, ex in enumerate(result.examples, start=1):
        mark = "✅" if ex["passed"] else "❌"
        input_preview = str(ex["input"])[:70].replace("|", "\\|")
        lines.append(f"| {i} | {mark} | {ex['score']:.2f} | {input_preview} |")
    return "\n".join(lines) + "\n"
