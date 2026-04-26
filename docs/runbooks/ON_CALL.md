# On-call runbook — SourceBox Sentry Command Center

> **Audience:** humans responding to a page or a customer report.
> **Goal:** find the actual problem fast, recover service, and write up
> what happened — without paging someone who can't help.

This runbook covers Command Center (the cloud service). For
CloudNode-side issues (a single customer's hardware misbehaving) see
the operator FAQ in `/docs#troubleshooting` — most of those are
self-serve.

The format is one section per scenario. Each section has the same
shape so you can scan it under pressure: **Symptoms**, **First
checks**, **Likely causes**, **Fix paths**, **When to escalate**.

---

## Quick reference

| Tool / link | Why |
|---|---|
| https://opensentry-command.fly.dev/api/health | Liveness — is the process up? |
| https://opensentry-command.fly.dev/api/health/detailed | DB ping latency, cache + queue depths |
| `fly logs -a opensentry-command` | Application stderr/stdout |
| `fly status -a opensentry-command` | Machine health + last deploy |
| `fly ssh console -a opensentry-command` | Shell into the live machine |
| Sentry: project **opensentry-command** | Alert origin, stack traces |
| Clerk dashboard | Auth issues, billing webhook deliveries |
| GitHub: `SourceBox-LLC/OpenSentry-Command` | Source, deploy via push to master |

---

## Scenario A: Sentry alert fired

**Symptoms.** Inbound email or webhook from Sentry referencing a
specific issue ID (e.g. `OPENSENTRY-COMMAND-1`).

**First checks.**
1. Open the Sentry issue. Read the stack trace and the most recent
   event's request context.
2. Check the issue's *frequency* and *first seen* timestamp. A
   spike on a brand-new exception is more urgent than a slow trickle
   of a known one.
3. Hit `/api/health/detailed` — does the broken subsystem show up
   there? (DB error → unhealthy. Big viewer-usage queue → degraded.)

**Likely causes.**
- A code path with no test coverage was hit by real production data.
  (Example: `OPENSENTRY-COMMAND-1` — `_log_cleanup_loop` chained
  `.union()` calls hit a CompoundSelect that has no `.union()`. Fix:
  `union(a, b, c, ...)` function form. Tests now in
  `backend/tests/test_log_cleanup_union.py` + `test_log_cleanup.py`.)
- An external dependency (Clerk, Fly database) is degraded.
- A recent deploy introduced a regression. Check `git log master --since=24.hours`.

**Fix paths.**
- **Hotfix and roll forward.** If the failing code is in Python or
  JS, write a regression test in `backend/tests/` or
  `frontend/tests/` first, then fix, then push to master. CI deploys
  via GitHub Actions; do **not** `fly deploy` directly — the deploy
  workflow is documented in `MEMORY.md` and ensures the right env
  variables are set.
- **Roll back.** If the deploy that introduced the bug is recent
  and the fix isn't obvious, `git revert <sha>` and push to master.
  Faster than chasing the root cause at 3am.

**When to escalate.**
- The exception is in the auth path (Clerk integration broken) and
  every customer is locked out.
- The exception fires at boot and the app is in a crash loop. Check
  `fly logs` and consider a pinned previous image.

---

## Scenario B: Customer reports "all my cameras are offline"

**Symptoms.** Single customer ticket; their dashboard shows every
camera in their org as offline; node heartbeats not coming through.

**First checks.**
1. From `fly logs`, search for the customer's `org_id` (find it
   via Clerk dashboard). Look for `[OfflineSweep]` log lines —
   these fire when the sweep flips a node/camera to offline.
2. Hit `/api/health/detailed` — is the SSE subscriber count zero?
   Is anything else degraded? If the DB is fine and other customers
   are streaming, this is likely customer-side.
3. Ask the customer: did they restart their CloudNode? Is the host
   machine on a network with outbound HTTPS to
   `opensentry-command.fly.dev`?

**Likely causes.**
- Customer's home internet dropped and the node hasn't reconnected.
- Customer's CloudNode crashed and didn't auto-restart. Their host
  machine's process supervisor (systemd, etc.) needs to bring it
  back up.
- The node's API key was rotated but the local config wasn't
  updated. Customer's `node.db` would show the old key hash.
- Their entire org was rebased to Free tier after a payment failure
  exceeded the 7-day grace window — the cameras beyond cap (5 on
  Free) would be `disabled_by_plan=True`, which presents as offline.
  Check the org's billing status in Clerk.

**Fix paths.**
- For credential-out-of-sync, walk the customer through the
  re-auth flow documented in `/docs#troubleshooting`.
- For payment-grace expiry, ask the customer to update their card
  in the Clerk billing portal. The grace flag clears on next webhook.
- For genuine node hangs, the customer needs hands-on access to
  the host machine. We cannot fix this remotely.

**When to escalate.**
- Multiple unrelated customers report the same symptom in the same
  hour — that's a Command Center problem masquerading as customer
  problems. Pivot to Scenario E.

---

## Scenario C: Customer reports "stream won't play"

**Symptoms.** Single customer; the dashboard loads, the camera tile
is visible, but clicking play shows the spinner forever or shows an
error overlay.

**First checks.**
1. In the customer's browser dev tools, check the network tab — is
   `/api/cameras/{id}/stream.m3u8` returning 200 or an error?
2. From `fly ssh console`, hit `/api/health/detailed` and check
   `checks.hls_cache.playlists_cached` — is it nonzero? If so, at
   least one customer is streaming.
3. Tail `fly logs` for the customer's `camera_id` and look for
   `[HLS]` or `[Cleanup]` lines that mention it.

**Likely causes.**
- Stream segments aged out of the in-memory cache. The segment
  cache is RAM-only, evicted after 60s of inactivity per camera.
  Customer has to refresh their browser to re-trigger the
  CloudNode → playlist push.
- Customer hit their viewer-hour cap for the month. The playback
  endpoint returns a clear error in the body — check the response.
- Customer's CloudNode stopped pushing segments. Their UI says
  "online" because the heartbeat is still landing, but the segment
  pipeline stalled. Common causes: ffmpeg process crashed,
  USB camera disconnected, host machine I/O saturated.

**Fix paths.**
- Cap-related: customer needs to upgrade or wait until the next
  calendar month rolls. We do not extend caps without an Order
  Form / Pro Plus paid agreement.
- Cache-related: ask the customer to refresh. If the issue persists
  longer than 60s, the CloudNode is probably the problem.
- CloudNode-side: customer-side troubleshooting — see
  `/docs#troubleshooting`.

**When to escalate.**
- Cache size in `/api/health/detailed` is *zero* but multiple
  customers are reporting playback failures at the same time. The
  CloudNode → backend `POST /push-segment` path may be broken.
  Check Fly logs for `403`, `429`, or `500` on that endpoint.

---

## Scenario D: Database is slow or unresponsive

**Symptoms.** `/api/health/detailed` shows
`checks.database.status == "error"` or
`latency_ms > 1000`. Sentry firing `OperationalError` or
`TimeoutError`.

**First checks.**
1. `fly status -a opensentry-command-db` (or whatever the Postgres
   app name is). Is it up?
2. `fly logs -a opensentry-command-db` for connection errors,
   replication lag, or out-of-disk warnings.
3. Check the Fly dashboard for the database app's CPU and memory
   metrics over the last hour.

**Likely causes.**
- Postgres ran out of disk. Logs will show `no space left on
  device`. Fly auto-extends in many cases; if not, manual disk
  expansion.
- Connection pool exhausted. SQLAlchemy's pool default is 5 with
  10 overflow. If the app process leaks connections (forgotten
  `db.close()` somewhere) the pool refills slowly.
- Long-running query holding a lock — usually triggered by a
  bad migration script or an unindexed query on a growing table.
  Check `pg_stat_activity` from a `fly postgres connect`.

**Fix paths.**
- Disk full: extend the volume via Fly.
- Pool exhausted: restart the app machine (`fly machine restart`)
  to drain the pool. Then root-cause the leak.
- Locked query: kill the offending PID via psql `SELECT
  pg_cancel_backend(pid)`.

**When to escalate.**
- After a restart the app comes back up but then degrades again
  within 5 minutes — that's a leak, not a transient. Get a second
  pair of eyes, root-cause before another restart.

---

## Scenario E: Multiple unrelated customers reporting issues at once

**Symptoms.** Three or more independent tickets in a short window.

**First checks.**
1. `/api/health/detailed` — every check should be green. Anything
   yellow or red explains it.
2. Fly status page (https://status.flyio.net/) — is our region
   degraded?
3. Clerk status page — is the auth provider down?
4. Sentry dashboard — is one specific exception spiking?

**Fix paths.**
- If Fly is down: post a status update to customers (email + the
  `#status` channel if you have one); wait it out; do not deploy
  during a regional incident.
- If Clerk is down: same — every signed-in user starts seeing 401s
  but the underlying app is fine. Wait for Clerk recovery.
- If Sentry shows a spike: jump to Scenario A with the most-fired
  issue.

**When to escalate.**
- Both Fly and Clerk green, no Sentry spike, but customers still
  report failures. Time to read the actual error responses they're
  getting. Ask for screenshots and the `request-id` from the
  network tab if present.

---

## Scenario F: Suspected data breach or unauthorized access

**Symptoms.** Anomalous Sentry traces showing access from
unexpected IPs; customer reports a stream session they didn't
initiate; an audit log row your monitoring flagged.

**First checks.**
1. Read the audit log row(s) in question — `audit_log` table —
   for context. Who, when, where (IP), what action.
2. Check whether the access used a JWT (Clerk session) or an MCP
   API key. The `event` and `user_id` columns disambiguate.

**Containment.**
- If an MCP API key was compromised: revoke it immediately via the
  admin dashboard. The hash is invalidated; further calls 401.
- If a Clerk session was compromised: ask the customer to sign out
  of all sessions in their Clerk account settings (this rotates
  the underlying token). Force-rotate from the Clerk dashboard if
  the user can't.
- If the cause is a vulnerability in our code: revert the offending
  change and ship a fix. Do **not** disclose the vulnerability
  details publicly until a fix is shipped (responsible disclosure).

**Notification.**
- If Customer Personal Data of an org was actually accessed by
  someone unauthorized, we have a 72-hour notification clock under
  the DPA (Section 4.7). Start drafting the customer notice while
  containment is in flight.
- Notify counsel; the legal record of the incident lives outside
  this repo. Don't write breach details into a GitHub issue.

**When to escalate.**
- Anything past containment.

---

## Scenario G: Customer requests deletion (GDPR / CCPA right to erase)

**Symptoms.** Customer submits a deletion request via support.

**First checks.**
1. Confirm the request is from a verified org admin. Identity hijack
   for "delete this org" is a real attack — verify via Clerk-known
   email at minimum.
2. Identify the org_id.

**Fix paths.**
- Self-service: walk the admin through Settings → Delete
  Organization. This deletes every node, camera, group, MCP key,
  audit log, stream access log, motion event, and settings row in
  a single transaction. There is no soft-delete.
- Manual: if self-service fails (e.g. a stuck row), `fly ssh
  console` and run the same cascade via psql. Document what you
  ran in the runbook log below.

**Records.**
- Log the deletion in your DSAR record-keeping system (outside this
  repo). Keep a record that the deletion happened, by whom, and on
  what date — but not the data itself.

**When to escalate.**
- The customer requests a deletion that includes Clerk account
  metadata. We cannot delete that from here — they have to delete
  their Clerk account themselves. Provide the Clerk
  account-deletion link.

---

## Scenario H: Pre-deploy sanity check before pushing master

> Not a fire — but if you're deploying at 11pm, walk through this
> checklist before pushing.

- `cd backend && python -m pytest` — must be green.
- `cd frontend && npm run build && npm run lint` — must be clean
  (lint warnings allowed; errors are not).
- `git log origin/master..HEAD` — read every commit message. If
  anything looks risky, postpone or coordinate.
- Hit `/api/health/detailed` on the live site — verify it's healthy
  *now* before you change it.
- Push. Watch GitHub Actions complete. Hit
  `/api/health/detailed` again.

---

## Runbook log

Append-only record of incidents we've actually responded to. Keep
each entry small — date, scenario, what we did, the take-away. The
goal is to build pattern recognition over time.

> No entries yet.

When you handle an incident, add it here. Future-you will thank
present-you.

---

## Updating this runbook

If you respond to something this runbook doesn't cover, add a new
scenario or extend an existing one *while it's fresh*. The runbook
is graded on whether it makes the next person's response faster,
not on whether it's pretty.
