function Notifications() {
  return (
    <section className="docs-section" id="notifications">
      <h2>Notifications<a href="#notifications" className="docs-anchor">#</a></h2>
      <p>
        SourceBox Sentry raises events for operational changes (nodes going offline, cameras
        dropping off) and motion activity. Each event flows through three channels:
        the in-app bell-icon panel, the email side-channel (opt-in per kind), and
        the MCP tool activity log.
      </p>

      <h3>What triggers a notification</h3>
      <ul>
        <li><strong>Node offline</strong> — Command Center hasn't received a heartbeat from a node for 90 seconds.</li>
        <li><strong>Node recovered</strong> — A previously offline node has started heartbeating again.</li>
        <li><strong>Camera offline</strong> — A camera on an online node stopped reporting segments (cable unplugged, USB error, camera held open by another app).</li>
        <li><strong>Camera recovered</strong> — A previously offline camera started reporting segments again.</li>
        <li><strong>Motion detected</strong> — A camera's FFmpeg scene-change scorer crossed the configured threshold. See <a href="#motion-detection">Motion Detection</a>.</li>
        <li><strong>Disk almost full</strong> — Command Center's persistent volume crossed 95% used. Recordings and audit logs start failing if you don't act.</li>
        <li><strong>Incident opened</strong> — A human or MCP agent filed a new incident report.</li>
      </ul>

      <h3>Where they show up</h3>
      <ul>
        <li>
          <strong>In-app inbox</strong> — Bell-icon panel in the top nav. SSE-powered,
          updates in real time. Audience-filtered: admin-only events stay hidden from
          regular members.
        </li>
        <li>
          <strong>Email</strong> — Opt-in per event kind via{" "}
          <a href="/settings#settings-notifications">notification settings</a>. v1
          ships with four kinds enabled by default for new orgs:
          <code>camera_offline</code>, <code>node_offline</code>,
          <code>disk_critical</code>, and <code>incident_created</code>.
          Recipients are derived from the event's audience field — admin-only events
          email only org admins; everyone-else events email all members. Every email
          carries a one-click unsubscribe link that disables that kind for the org.
        </li>
        <li><strong>Incidents tab</strong> — Any notification filed as an incident appears there for triage.</li>
        <li><strong>MCP tool log</strong> — Admin dashboard shows every MCP call, including ones that fired on a motion event.</li>
      </ul>

      <h3>Email delivery details</h3>
      <p>
        Emails go through Resend (US-based transactional provider — see{" "}
        <a href="/legal/sub-processors">sub-processors</a> for the disclosure).
        The Command Center holds a small EmailOutbox per pending send; a background
        worker drains it every 5 seconds. Median time-to-inbox after the triggering
        event is under 10 seconds for the operator-critical kinds.
      </p>
      <p>
        <strong>Bounce + complaint handling:</strong> if a recipient address bounces
        or marks an email as spam, Resend webhooks tell us, we add the address to a
        local suppression list, and the worker stops sending to it. No further config
        needed.
      </p>

      <div className="docs-callout docs-callout-info">
        <p>
          <span className="docs-callout-icon">ℹ️</span>
          <span>
            <strong>Motion-event emails are intentionally deferred.</strong> Sending an
            email per motion event without per-camera cooldown + digest mode would
            blast hundreds of messages a day on any active outdoor camera, get marked
            as spam, and tank deliverability for everyone. They'll ship in v1.1 with
            proper rate-limit + digest logic. Until then, motion stays in the in-app
            inbox; for live external alerts on motion, point an MCP agent (Claude,
            Cursor, your own) at the motion stream and route to your own transport.
          </span>
        </p>
      </div>

      <div className="docs-callout docs-callout-info">
        <p>
          <span className="docs-callout-icon">ℹ️</span>
          <span>
            <strong>SMS and mobile push: not built in.</strong> Wire an MCP agent to
            Twilio, PagerDuty, or your existing webhook if you need them — every
            plan has full MCP access.
          </span>
        </p>
      </div>
    </section>
  )
}

export default Notifications
