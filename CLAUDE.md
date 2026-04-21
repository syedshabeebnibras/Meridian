# Meridian — Project Operating Instructions

These instructions govern every session in this repo. They override session defaults. Follow them for the whole project.

---

## Core Principles

- **Simplicity First** — Make every change as simple as possible. Touch the minimum amount of code needed.
- **No Laziness** — Find root causes. No temporary fixes. Senior-engineer standards only.
- **Minimal Impact** — Only touch what's necessary. No side effects; no new bugs introduced by the fix.

---

## Workflow Orchestration

### 1. Plan Mode by Default
- Enter plan mode for any non-trivial task (≥3 steps or any architectural decision).
- If something goes sideways mid-execution, **stop and re-plan immediately** — do not push through.
- Use plan mode for verification steps too, not just building.
- Write detailed specs upfront to reduce ambiguity.

### 2. Subagent Strategy
- Use subagents liberally to keep the main context window clean.
- Offload research, exploration, and parallel analysis to subagents.
- For complex problems, throw more compute at it via parallel subagents.
- One task per subagent — keep them focused.

### 3. Self-Improvement Loop
- After **any** correction from the user, update `tasks/lessons.md` with the pattern.
- Write rules for yourself that prevent the same mistake.
- Iterate ruthlessly on these lessons until the mistake rate drops.
- Review `tasks/lessons.md` at session start for relevant rules.

### 4. Verification Before Done
- Never mark a task complete without proving it works.
- Diff behavior between main and your changes when relevant.
- Ask: *"Would a staff engineer approve this?"*
- Run tests, check logs, demonstrate correctness — evidence before assertions.

### 5. Demand Elegance (Balanced)
- For non-trivial changes, pause and ask: *"Is there a more elegant way?"*
- If a fix feels hacky: *"Knowing everything I know now, implement the elegant solution."*
- Skip this gate for simple, obvious fixes — don't over-engineer.
- Challenge your own work before presenting it.

### 6. Autonomous Bug Fixing
- When given a bug report: **just fix it**. Don't ask for hand-holding.
- Point at logs, errors, failing tests — then resolve them.
- Zero context switching required from the user.
- Go fix failing CI tests without being told how.

---

## Task Management Protocol

Every non-trivial task flows through `tasks/todo.md`:

1. **Plan First** — Write the plan to `tasks/todo.md` as a checkable list.
2. **Verify Plan** — Check in with the user before starting implementation.
3. **Track Progress** — Mark items complete as you go.
4. **Explain Changes** — Give a high-level summary at each step.
5. **Document Results** — Append a review section to `tasks/todo.md` when done.
6. **Capture Lessons** — Update `tasks/lessons.md` after any correction.

---

## Quick Reference

| Situation | Action |
|---|---|
| Task ≥ 3 steps or architectural | Enter plan mode; write `tasks/todo.md` |
| User corrects me | Update `tasks/lessons.md` with the rule |
| Fix feels hacky | Stop; re-implement the elegant version |
| Complex research/exploration | Dispatch subagents in parallel |
| About to claim "done" | Prove it: tests, logs, diffs |
| Bug report arrives | Fix autonomously; don't ask how |
