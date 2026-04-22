# Launch Plan

Phase 8 of the execution plan — controlled production rollout with
monitoring. This document is the one-stop reference for running the
launch; every concrete decision is gated on the go/no-go script.

---

## Rollout stages

| # | Stage | Traffic share | Duration | Gate before next stage |
|---|---|---|---|---|
| 1 | **Dogfood** | AI team (5 users, allowlist) | 2 days | zero P1 bugs + team sign-off |
| 2 | **Limited beta** | 50 beta testers (allowlist) | 3 days | `scripts/go_no_go.py` + positive feedback majority |
| 3 | **25% rollout** | percentage=25 | 1 day | stability monitor clean + P1=0 |
| 4 | **50% rollout** | percentage=50 | 1 day | stability monitor clean + P1=0 |
| 5 | **100% rollout** | percentage=100 | ongoing | 48-hour stability → Section-12 exit criterion met |

Every transition runs through the same helper:

```bash
scripts/go_no_go.py               # gate check
scripts/rollout.py set --percentage <N>
scripts/stability_monitor.py --mode watch --hours 24
```

---

## Day-0 sequence (dogfood)

```bash
# 1. Starting state: flag at 0% with kill-switch off.
scripts/rollout.py status

# 2. Allowlist the AI team (they bypass the percentage rule).
for user in u_alice u_bob u_carol u_dan u_erin; do
  scripts/rollout.py allow --user $user
done

# 3. Every dogfood team member logs in and runs a handful of queries.
#    Thumbs-up/down feedback flows via POST /v1/feedback.

# 4. 48 hours later, run the stability monitor:
STAGING_URL=https://meridian.internal scripts/stability_monitor.py --mode watch --hours 48

# 5. If zero P1 incidents, proceed to beta.
```

---

## Day-2 → Day-4 (limited beta, 50 users)

```bash
# Ingest the 50 beta testers (one per line in ops/beta_users.txt).
for user in $(cat ops/beta_users.txt); do
  scripts/rollout.py allow --user $user
done

# Beta window: 3 days. Collect feedback.
# At the end, run go/no-go:
STAGING_URL=https://meridian.internal scripts/go_no_go.py
```

---

## Day-5+ (percentage rollout)

Section 12 calls for 25% → 50% → 100%. Each bump is a separate
decision — don't script them as a single command.

```bash
# 25%
scripts/go_no_go.py && scripts/rollout.py set --percentage 25
# watch 24 hours
scripts/stability_monitor.py --mode watch --hours 24 --output /tmp/stab_25.md

# 50%
scripts/go_no_go.py && scripts/rollout.py set --percentage 50
scripts/stability_monitor.py --mode watch --hours 24 --output /tmp/stab_50.md

# 100%
scripts/go_no_go.py && scripts/rollout.py set --percentage 100
scripts/stability_monitor.py --mode watch --hours 48 --output /tmp/stab_100.md
```

The final 48-hour watch against `--percentage 100` is what satisfies
the Section 12 exit criterion.

---

## Emergency rollback

Any on-call authority can flip the kill switch instantly:

```bash
scripts/rollout.py kill --on
```

Everyone (including allowlisted users) gets the "not enabled" response
until `scripts/rollout.py kill --off`.

For a graceful roll-back (e.g. observed faithfulness drop at 50%):

```bash
scripts/rollout.py set --percentage 25   # drop back one stage
scripts/stability_monitor.py --mode watch --hours 1
# investigate, then either re-promote or hold
```

---

## Communications

| When | What | Where |
|---|---|---|
| Dogfood start | "Meridian dogfood starts today, AI team only" | #meridian-feedback |
| Beta start | Beta kickoff message + `comms/feedback-form.md` link | email to 50 testers + #meridian-feedback |
| 25% rollout | "Meridian is rolling out to 25% of users today" | #announcements |
| 100% rollout | `comms/launch-announcement.md` | all-hands email + #announcements |

Usage guide: `comms/usage-guide.md`. Publish to the company wiki before
the 25% stage.

---

## Exit-criteria checklist (Section 12 Phase 8)

- [ ] 100% rollout stable for 48 hours — `scripts/stability_monitor.py --mode watch --hours 48` returns zero P1 incidents
- [ ] Zero P1 incidents during entire rollout window
- [ ] User feedback collected — `POST /v1/feedback` endpoint has ≥ N
      entries from the beta + dogfood windows (N picked by AI/Prompt team)

Once all three are checked, Phase 8 is done and Phase 9 (post-launch
optimisation) begins.
