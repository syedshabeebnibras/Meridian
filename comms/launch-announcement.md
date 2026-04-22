# Launch announcement — template

Paste into email (all-hands) and Slack (#announcements) on the day of
full 100% rollout. Fill in bracketed values.

---

**Subject:** Meridian is now live for every internal user

Hi everyone,

Starting today, **Meridian** — our internal knowledge assistant — is
available to every [Company] employee at **[https://meridian.internal]**.

Meridian answers questions grounded in our existing docs (Confluence
runbooks, engineering ADRs, policy libraries, product specs) with cited
sources, extracts structured data from contracts and spec docs, and can
trigger simple workflows like creating a Jira ticket or posting to a
Slack channel — all with natural-language prompts.

### What you can ask

- "What's the escalation procedure for a P1 database outage?"
- "Summarize the SLA terms for our Enterprise tier."
- "Create a Jira ticket for the auth service memory leak."
- "Who owns the billing migration project?"

### What Meridian won't do

- Answer questions the docs don't cover — it'll tell you so, and suggest
  where to look instead.
- Make decisions about people (performance, comp, hiring).
- Reach outside our internal document index (no public web, no
  non-company SaaS data).

### Feedback matters

Every response has thumbs-up / thumbs-down buttons. If Meridian gives
you a bad answer, **please click thumbs-down and tell us why** — we
review every negative signal weekly and it's the fastest way for us to
improve.

### Known limits

- In v1, Meridian is English-only.
- Tool actions (ticket creation, Slack posts) always ask for
  confirmation before executing. That's intentional.
- Responses can take 2–4 seconds for complex questions. Please be
  patient on the first response; we cache aggressively so follow-ups
  should be faster.

### Help + escalation

- Documentation: **[link to usage guide]**
- Feedback channel: **#meridian-feedback** in Slack
- Production incident: page the on-call via PagerDuty
  (service: `meridian-orchestrator`)

Thanks to everyone on the platform, data, security, and AI teams who
got us here.

— [Your Name]
[Your Title]
