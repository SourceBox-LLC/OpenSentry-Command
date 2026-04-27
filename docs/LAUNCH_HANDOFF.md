# Launch handoff — what only you can do

> **Audience:** Sb (you, the operator).
> **Goal:** every code-side launch blocker I (Claude) could close has
> been closed and committed. What's left is everything that needs a
> credit card, a signature, hardware, or a human decision — none of
> which I can do for you.

This list is sequenced by *order-of-operations*, not by importance.
Tackle the dependencies first (auth, transports) so the later items
(legal, support process) have something to point at.

---

## 1. Clerk production keys

**State now.** The dashboard is using Clerk's test keys (`pk_test_*`,
`sk_test_*`). These work end-to-end for auth and billing in the
sandbox, but they're scoped to the test environment — real Stripe
charges don't post, the dev-mode badge shows in the UI, and the
"Clerk dev keys in prod" memory note documents this is intentional
*for now*.

**What you need to do.**
1. In the Clerk dashboard, switch the application to production
   mode (or create a separate production app and copy the
   user/organization schema across — Clerk has a one-click clone for
   this).
2. Configure the production Stripe account via Clerk's billing tab
   (Clerk handles Stripe under the hood per
   `MEMORY.md::project_billing_stack`).
3. Update Fly secrets:
   ```
   fly secrets set \
     CLERK_PUBLISHABLE_KEY=pk_live_... \
     CLERK_SECRET_KEY=sk_live_... \
     -a opensentry-command
   ```
4. Verify the Clerk webhook endpoint
   `https://opensentry-command.fly.dev/api/webhooks/clerk` is
   registered in the production Clerk app and signing secret is set
   (`CLERK_WEBHOOK_SECRET`). Test by upgrading a test org and
   confirming the `Setting(org_plan="pro")` row shows up.

**Verification.** After the secret swap, sign out and sign back in.
The dev-mode badge in the corner should disappear.

---

## 2. Notification transport signup (optional, for an alerts feature)

**State now.** The product explicitly does NOT ship email/SMS/push.
The recent docs/security/pricing copy makes this gap loud (per the
"Honest gaps" section on `/security` and the FAQ entries on
`/pricing` and `/docs`). MCP-driven external alerting works on every
plan today.

**What to do later, if you decide to build it.**
1. Pick a transport. For email, Resend is cheapest for low volume
   ($0 up to 3K/month), Postmark is more reliable for transactional.
   For SMS, Twilio is the obvious choice. **SMS is explicitly out of
   scope per the `project_notification_channels` memory note** — be
   deliberate about reversing that decision; it's a support burden.
2. Wire a transport adapter into `backend/app/api/notifications.py`
   alongside the existing `notification_broadcaster` SSE path.
3. Update the disclaimer copy on `/pricing`, `/security`, and `/docs`
   to remove the "we don't ship this" caveat. Search for the string
   `built into Command Center` to find every spot.

**Status before you ship this.** Email and SMS introduce new
sub-processors. Update `docs/legal/SUB_PROCESSORS.md` *before*
turning the transport on, and notify customers per the 14-day notice
policy in the DPA.

---

## 3. Status page vendor (recommended)

**State now.** I added `/api/health/detailed` (commit `9cd7a5b`)
which any status page can poll. There's no public status page yet.

**Options.**
- **Instatus** ($20/mo for the smallest paid plan, free tier works
  for solo operations).
- **Statuspage.io** by Atlassian (more features, pricier).
- **Hosted-bytes** / **BetterStack** — modern alternatives.

**What to do.**
1. Create a status page on the chosen vendor.
2. Configure a "synthetic monitor" to GET
   `/api/health/detailed` every minute. Treat `status: unhealthy` or
   any 5xx as down.
3. Link the status page from `/security` (replace the placeholder
   "No public status page yet" line in the "Honest gaps" section).
4. Subscribe customers to status updates via the vendor's
   subscription widget — automatic for most.

---

## 4. Domain / DNS

**State now.** Live on `opensentry-command.fly.dev`. CORS is
hard-coded for that origin (`backend/app/main.py::cors_origins`).

**To switch.**
1. Buy a domain (e.g. `sentry.sourceboxlabs.com`).
2. Add a Fly cert via `fly certs add`.
3. Update `cors_origins` in `app/main.py` to include the new
   domain.
4. Update `FRONTEND_URL` env var on Fly.
5. Update Clerk's allowed origins to include the new domain.
6. Update `install.sh` (Linux/macOS) so it points at the new base URL
   — this URL gets baked into customer CloudNodes at install time, so
   transitioning takes weeks. The Windows MSI doesn't need a parallel
   update because it's a static download from GitHub Releases (the
   MSI's URL doesn't change with the Command Center domain).

---

## 5. Sentry production setup

**State now.** Sentry initialisation lives in
`backend/app/main.py::init_sentry`, only fires when `SENTRY_DSN` is
set. The on-call runbook references Sentry for triage; you have an
existing alert (`OPENSENTRY-COMMAND-1`) so it's already partially
wired.

**Verify.**
1. `fly secrets list -a opensentry-command` — `SENTRY_DSN` should
   be set.
2. Check `SENTRY_TRACES_SAMPLE_RATE` — currently defaults to a low
   number; for production you may want `0.1` (10%).
3. Enable email alerting in Sentry for new issues (it's how you got
   the `OPENSENTRY-COMMAND-1` email, so probably already on — but
   verify the rule fires for *all* environments, not just dev).

---

## 6. Lawyer review of legal templates

**State now.** I wrote `docs/legal/DPA.md` and
`docs/legal/SUB_PROCESSORS.md` as engineering-truth working drafts.
Both lead with `DRAFT — NOT FOR EXECUTION` so nobody can sign them
accidentally.

**What you need to do.**
1. Find a privacy lawyer. Many SaaS-friendly firms have flat-fee
   "starter DPA review" packages for early-stage companies in the
   $1.5–4K range.
2. Send them the markdown drafts. They will return a redlined PDF.
3. Save the lawyer-approved PDF in your records system (NOT in this
   repo — the markdown stays as the engineering record).
4. When sub-processors change, update `SUB_PROCESSORS.md` in master
   and email the billing contact (per the DPA's 14-day notice
   policy). The repo edit IS the public notice.

**Other legal templates you may need that I haven't drafted.**
- Terms of Service (the existing `/legal` page has an outline; have
  the lawyer review it).
- Privacy Policy (same — check `/legal`).
- Acceptable Use Policy (probably worth one, given the camera
  context — what users *cannot* point cameras at).

---

## 7. Backups and disaster recovery

**State now.** Fly's managed Postgres has automated daily snapshots
retained per their default schedule.

**What you need to do.**
1. Verify the snapshot schedule in the Fly dashboard.
2. **Test a restore.** This is the only thing that turns "we have
   backups" from a claim into a fact. Do this at least once before
   you onboard the first paying customer:
   - Spin up a fresh Fly Postgres app.
   - Restore the latest snapshot of production into it.
   - Run `python -m pytest backend/tests/test_*.py` against the
     restored DB to confirm schema integrity.
3. Document the restore procedure in
   `docs/runbooks/DISASTER_RECOVERY.md` (I haven't written this
   one — wait until you've done a real restore so you can capture
   what actually broke).

---

## 8. Pi performance benchmark

**State now.** The CloudNode README and the `/docs` site describe
the node as running on "any Linux, macOS, or Windows machine,
including a Raspberry Pi". I haven't validated that actually works
under a realistic camera load.

**What you need to do.**
1. Get a Pi 4 (or Pi 5, increasingly common). Install OpenSentry
   CloudNode via the install script.
2. Connect 1, 2, 4 USB cameras at 1080p / 30fps and watch:
   - CPU steady-state under load.
   - Memory steady-state.
   - Egress bandwidth to Command Center.
   - Whether motion detection completes within the segment window.
3. Document the result somewhere — at minimum in
   `OpenSentry-CloudNode/README.md` under a "Performance reference"
   section. If a Pi 4 only handles 2 cameras at 1080p, that's
   useful for users to know upfront. If it handles 8, even better.

**If the Pi turns out to be too weak for the advertised use case,**
update the docs honestly. Better to say "Pi 5 recommended for 4+
cameras" than to lose a customer who tried it on a Pi 3.

---

## 9. GitHub repo settings

**State now.** Master branch with no protection rules.

**Recommended.**
- Branch protection on `master`: require status checks (CI), require
  linear history (no merge commits), require pull request reviews
  (1 approver) once you have a co-maintainer.
- Required status checks: `pytest backend/tests`, `npm run build`,
  `npm run lint`.
- Dependabot security updates: already on (closed PR #8 was
  Dependabot's). Worth verifying the schedule.

---

## 10. Customer support process

**State now.** Support routes are described in the legal page and
implied in the DPA, but no actual support inbox is configured.

**What you need to do.**
1. Set up a `support@yourdomain.tld` mailbox. Forward to your
   personal email or use Front / Help Scout for triage if volume
   warrants.
2. Define an internal target: respond to first email within X
   business hours. Don't promise an SLA on the public site at the
   Free / Pro tiers (the security page already says "No formal SLA
   on Free or Pro").
3. Document common questions in `/docs#faq` (already pretty good)
   so customers can self-serve.

---

## 11. On-call rotation

**State now.** You're a one-person team. The runbook
(`docs/runbooks/ON_CALL.md`) is written as if any human can pick up
a page.

**What you need to do later.**
1. As soon as you have a second engineer / co-maintainer, define a
   PagerDuty (or alternative) rotation.
2. Update the runbook with rotation contact info.
3. The runbook itself doesn't change — it's already in the
   "scannable under pressure" shape.

---

## 12. Final go/no-go checklist (to run the day before launch)

```
[ ] Clerk production keys swapped (item 1)
[ ] Backup restore tested at least once (item 7)
[ ] DPA + sub-processors PDF on file with lawyer signoff (item 6)
[ ] Status page live and pointed at /api/health/detailed (item 3)
[ ] Sentry alerts confirmed firing in production env (item 5)
[ ] Custom domain (if applicable) live + Clerk allows it (item 4)
[ ] Branch protection enabled on master (item 9)
[ ] Support inbox configured and monitored (item 10)
[ ] Run `python -m pytest` in backend/ — all green
[ ] Run `npm run build && npm run lint` in frontend/ — all green
[ ] Browse the live site at 375px, 1024px, 1440px — nothing broken
[ ] Hit /api/health/detailed — status is "healthy", DB latency < 50ms
```

When all twelve check, ship the launch announcement.

---

> *Closed by Claude on 2026-04-25. Every code-side blocker the
> assistant could close is committed on master. Everything in this
> file requires you.*
