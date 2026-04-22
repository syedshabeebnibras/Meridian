# Meridian — Usage Guide

A short reference for internal users. Post in #meridian-feedback when
publishing a new version.

---

## What Meridian does

**Meridian is an internal knowledge assistant.** It searches our
indexed docs, synthesizes an answer, and cites its sources. It can also
trigger structured actions (creating a Jira ticket, posting to Slack)
on your behalf.

### Question types Meridian handles well

1. **Grounded Q&A** — "What is our incident response procedure for P1?"
2. **Structured extraction** — "Extract the SLA parameters from the
   Enterprise contract template."
3. **Tool actions** — "Create a Jira ticket for the auth memory leak
   we discussed."
4. **Policy lookups** — "How long do we retain customer logs?"

### Question types Meridian doesn't handle

- General knowledge ("What's the capital of France?") — out of scope.
- Code generation ("Write Python to sort a list") — out of scope.
- Personal / HR questions ("What's Alice's salary?") — blocked by PII
  guardrails even if that data were indexed.
- Questions where the indexed docs disagree or don't cover the topic
  — Meridian will say "I don't have enough information" and suggest
  where to look.

---

## Tips for getting good answers

- **Be specific.** "SLA for Enterprise" beats "SLA".
- **Reference doc names or product areas** when you know them. Meridian
  uses those as retrieval hints.
- **For tool actions, say what you want clearly**: "Create a Jira
  ticket in ENG, type bug, priority high, titled ..." — Meridian will
  confirm before executing.
- **Use follow-ups.** If an answer is incomplete, "expand on X" or
  "what about Y?" will usually work within the same session.

---

## What happens behind the scenes (if you're curious)

1. Your query runs through PII and injection-detection guardrails.
2. A small classifier routes it to the right workflow (Q&A, extraction,
   tool action, or clarification).
3. The appropriate Claude or GPT-4 tier handles it, grounded in
   retrieved doc chunks.
4. The response is validated (schema, citations, refusal consistency)
   before you see it.
5. Every trace is logged to Langfuse for audit.

---

## Feedback

Every answer has 👍 / 👎 buttons. Use them.

- 👍 keeps Meridian's prompts + model choices stable.
- 👎 with a comment triggers a weekly review — those become the
  highest-priority improvements.

For urgent issues, use **#meridian-feedback** in Slack or file a Jira
ticket tagged `meridian-prod`.

---

## Privacy and auditability

- Every request you make is logged (query, response, citations,
  timestamp) and retained for 90 days.
- PII detected in your input is redacted before the model sees it.
- Responses that would leak PII are blocked.
- Your usage data is visible to the Meridian team for quality review
  — not to anyone outside the team, and never to other users.

---

## When Meridian gets it wrong

It will. Sometimes the answer is stale because the underlying doc is
old. Sometimes a policy interpretation is genuinely ambiguous. **Always
treat Meridian as a starting point**, not the final authority. The
cited source is the authority.
