import { PricingTable } from "@clerk/clerk-react"

function PricingPage() {
  return (
    <div className="pricing-page">
      <div className="pricing-glow pricing-glow-1"></div>
      <div className="pricing-glow pricing-glow-2"></div>

      <div className="pricing-hero">
        <div className="pricing-badge">PRICING</div>
        <h1 className="pricing-title">
          Connect as many cameras as you need.<br />
          <span className="pricing-title-accent">Pay for how much you actually watch.</span>
        </h1>
        <p className="pricing-subtitle">
          Your monthly viewer-hours are the real tier differentiator — not
          how many cameras you plug in. Recording to your CloudNode is
          always local and never counts against your cap.
        </p>
      </div>

      <div className="pricing-table-wrapper">
        <PricingTable for="organization" />
      </div>

      {/* Detailed plan comparison — the Clerk PricingTable above only
          shows what the operator has configured as each plan's feature
          list in the Clerk dashboard. This block is the source of truth
          for what each tier actually buys, organised so a scanning
          visitor can find their use case without reading the whole page.
          If you change a number here, also change it in /docs#plans and
          in backend/app/core/plans.py::PLAN_LIMITS. */}
      <div className="pricing-detail">
        <h2 className="pricing-detail-title">What each plan buys you</h2>
        <p className="pricing-detail-intro">
          Below is the complete, per-tier breakdown. Everything on this
          page is enforced in code — our open-source repos are the source
          of truth, and the numbers match exactly.
        </p>

        <div className="pricing-detail-grid">

          {/* Free — designed to be usable long-term for home users,
              not a hobbled trial. The "for who" lines are important;
              they let visitors self-identify without reading numbers. */}
          <div className="pricing-detail-card pricing-detail-free">
            <div className="pricing-detail-card-head">
              <h3>Free</h3>
              <div className="pricing-detail-price">$0<span>/mo</span></div>
              <p className="pricing-detail-for">For home users with a few cameras they check occasionally.</p>
            </div>

            <div className="pricing-detail-section">
              <div className="pricing-detail-section-label">Usage</div>
              <ul>
                <li><strong>30 viewer-hours / month</strong> of live playback</li>
                <li>Up to <strong>5 cameras</strong> across <strong>2 CloudNodes</strong></li>
                <li><strong>2 team seats</strong></li>
                <li>10 concurrent live-dashboard connections</li>
              </ul>
            </div>

            <div className="pricing-detail-section">
              <div className="pricing-detail-section-label">Included</div>
              <ul>
                <li>Live HLS streaming + snapshots</li>
                <li>Local recording to your CloudNode (unlimited, unmetered)</li>
                <li>On-device motion detection + alerts</li>
                <li>Encrypted recordings + API key (AES-256-GCM)</li>
                <li>Camera groups</li>
                <li>30-day log retention</li>
              </ul>
            </div>

            <div className="pricing-detail-section">
              <div className="pricing-detail-section-label">Not included</div>
              <ul className="pricing-detail-missing">
                <li>Admin dashboard + stream analytics</li>
                <li>MCP integration (AI access)</li>
                <li>Outbound webhooks</li>
                <li>Priority support</li>
              </ul>
            </div>
          </div>

          {/* Pro — the conversion target. Highlighted visually so
              a first-time visitor's eye naturally lands here. The
              "adds over Free" framing makes the upgrade story obvious. */}
          <div className="pricing-detail-card pricing-detail-pro pricing-detail-featured">
            <div className="pricing-detail-featured-badge">Most popular</div>
            <div className="pricing-detail-card-head">
              <h3>Pro</h3>
              <div className="pricing-detail-price">
                $12<span>/mo</span>
                <div className="pricing-detail-annual">or $10/mo billed annually ($120/yr)</div>
              </div>
              <p className="pricing-detail-for">For small businesses, prosumer setups, and anyone who wants AI access.</p>
            </div>

            <div className="pricing-detail-section">
              <div className="pricing-detail-section-label">Usage</div>
              <ul>
                <li><strong>300 viewer-hours / month</strong> — 10× Free</li>
                <li>Up to <strong>25 cameras</strong> across <strong>10 CloudNodes</strong></li>
                <li><strong>10 team seats</strong></li>
                <li>30 concurrent live-dashboard connections</li>
              </ul>
            </div>

            <div className="pricing-detail-section">
              <div className="pricing-detail-section-label">Everything in Free, plus</div>
              <ul>
                <li><strong>Admin dashboard</strong> — stream access logs, usage analytics</li>
                <li><strong>MCP integration</strong> — connect Claude, Cursor, or custom agents</li>
                <li><strong>MCP rate limit:</strong> 30 calls/min · 5,000 calls/day per key</li>
                <li><strong>Danger-zone tools</strong> — log wipe, full-reset, key rotation</li>
                <li>90-day log retention</li>
                <li>Email support</li>
              </ul>
            </div>
          </div>

          {/* Pro Plus — positioned against integration-heavy use cases
              (multi-site, MSPs, compliance-driven ops). Outbound webhooks
              are the headline feature; scale is secondary. */}
          <div className="pricing-detail-card pricing-detail-pro-plus">
            <div className="pricing-detail-card-head">
              <h3>Pro Plus</h3>
              <div className="pricing-detail-price">
                $29<span>/mo</span>
                <div className="pricing-detail-annual">or $25/mo billed annually ($300/yr)</div>
              </div>
              <p className="pricing-detail-for">For multi-site operators, MSPs, and anyone pushing events into their own stack.</p>
            </div>

            <div className="pricing-detail-section">
              <div className="pricing-detail-section-label">Usage</div>
              <ul>
                <li><strong>1,500 viewer-hours / month</strong> — 5× Pro</li>
                <li>Up to <strong>200 cameras</strong> across <strong>unlimited CloudNodes</strong></li>
                <li><strong>20 team seats</strong></li>
                <li>100 concurrent live-dashboard connections</li>
              </ul>
            </div>

            <div className="pricing-detail-section">
              <div className="pricing-detail-section-label">Everything in Pro, plus</div>
              <ul>
                <li><strong>Outbound webhooks</strong> — push motion / camera / node events to your own HTTPS endpoint (PagerDuty, Zapier, ticketing, home automation)</li>
                <li>HMAC-SHA256 signed deliveries with automatic retry + auto-disable</li>
                <li><strong>MCP rate limit:</strong> 120 calls/min · 30,000 calls/day per key (4× Pro)</li>
                <li><strong>365-day log retention</strong> — full year of audit history</li>
                <li><strong>Priority support</strong> — 24-hour first-response SLA</li>
              </ul>
            </div>
          </div>
        </div>

        <p className="pricing-detail-footnote">
          Need higher caps? If you legitimately need more than 200 cameras
          or 1,500 viewer-hours per month, email{" "}
          <a href="https://github.com/SourceBox-LLC" target="_blank" rel="noopener noreferrer">
            SourceBox LLC
          </a>{" "}
          — we'd rather raise your bucket than lose a real customer to an
          arbitrary ceiling.
        </p>
      </div>

      <div className="pricing-features">
        <h2 className="pricing-features-title">How usage-based pricing works</h2>
        <div className="pricing-features-grid">
          <div className="pricing-feature-item">
            <div className="pricing-feature-icon">⏱️</div>
            <h3>Viewer-hours, not cameras</h3>
            <p>Every second of live video played to an authenticated viewer counts. A camera you never watch costs nothing against your cap.</p>
          </div>
          <div className="pricing-feature-item">
            <div className="pricing-feature-icon">💾</div>
            <h3>Recordings don't count</h3>
            <p>Local recording to your CloudNode's encrypted SQLite is unlimited and free. Only cloud-served live playback is metered.</p>
          </div>
          <div className="pricing-feature-item">
            <div className="pricing-feature-icon">📊</div>
            <h3>Live usage display</h3>
            <p>See exactly how many hours you've used this month on the dashboard. No surprises, no overage billing — we cap, we don't charge extra.</p>
          </div>
          <div className="pricing-feature-item">
            <div className="pricing-feature-icon">🔐</div>
            <h3>Encrypted end to end to disk</h3>
            <p>TLS in flight, AES-256-GCM on the CloudNode at rest. A stolen drive is unreadable elsewhere.</p>
          </div>
          <div className="pricing-feature-item">
            <div className="pricing-feature-icon">🚫</div>
            <h3>No analytics, no trackers</h3>
            <p>No Mixpanel, no Segment, no ad networks, no data brokers. Verifiable with a grep of our open source.</p>
          </div>
          <div className="pricing-feature-item">
            <div className="pricing-feature-icon">🖥️</div>
            <h3>Runs on your hardware</h3>
            <p>CloudNode (GPL-3) installs on any Linux, macOS, or Windows machine. Use a Pi, a NUC, or an old laptop.</p>
          </div>
        </div>
      </div>

      <div className="pricing-faq">
        <h2 className="pricing-faq-title">Common questions</h2>
        <div className="pricing-faq-grid">
          <div className="pricing-faq-item">
            <h3>What counts as a "viewer-hour"?</h3>
            <p>One viewer-hour = one hour of live video played to an authenticated browser session. Background tabs that keep pulling segments count; idle cameras with no one watching don't. Recordings stored on your CloudNode are unlimited and free — they never count against your cap.</p>
          </div>
          <div className="pricing-faq-item">
            <h3>What happens when I hit my viewer-hour cap?</h3>
            <p>Live playback pauses with an upgrade prompt until the next calendar month begins. Your cameras keep recording locally, your motion events still fire, and your CloudNode keeps running. You just can't stream video live to the dashboard until your cap resets or you upgrade.</p>
          </div>
          <div className="pricing-faq-item">
            <h3>Can I upgrade or downgrade anytime?</h3>
            <p>Yes. Upgrades take effect immediately. Downgrades apply at the end of the current billing period. Annual plans save roughly 17% versus the monthly price.</p>
          </div>
          <div className="pricing-faq-item">
            <h3>Do you bill for overage?</h3>
            <p>No. Your monthly bill is exactly the plan price, always. When you hit a cap we pause the metered feature (live playback or MCP calls) rather than surprise-charge you.</p>
          </div>
          <div className="pricing-faq-item">
            <h3>What if my payment fails?</h3>
            <p>Your account enters a 7-day grace period during which the charge is retried automatically. Your cameras keep streaming throughout. After 7 days without a successful payment, cameras beyond the Free-tier limit are suspended and you're rebased to Free-tier viewer-hours. Updating your card resumes everything immediately.</p>
          </div>
          <div className="pricing-faq-item">
            <h3>Why are camera counts still capped?</h3>
            <p>They're abuse rails, not product tiers. Every connected camera continuously pushes segments to our cache even when idle, which drives our backend load. The caps (5 / 25 / 200) are well above what any realistic customer needs. If you legitimately need more, email us and we'll raise yours.</p>
          </div>
          <div className="pricing-faq-item">
            <h3>Is the CloudNode software free?</h3>
            <p>Yes, always. CloudNode is open source (GPL-3) and runs on your own hardware. You only pay for the Command Center cloud service — and you can self-host that too (AGPL-3) if you want to skip us entirely.</p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default PricingPage
