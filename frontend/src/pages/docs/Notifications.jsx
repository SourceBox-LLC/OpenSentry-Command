function Notifications() {
  return (
    <section className="docs-section" id="notifications">
      <h2>Notifications<a href="#notifications" className="docs-anchor">#</a></h2>
      <p>
        SourceBox Sentry raises events for operational changes (nodes going offline, cameras
        dropping off) and motion activity. These show up as in-dashboard banners and
        feed into the MCP tool activity log.
      </p>

      <h3>What triggers a notification</h3>
      <ul>
        <li><strong>Node offline</strong> — Command Center hasn't received a heartbeat from a node for 90 seconds.</li>
        <li><strong>Node recovered</strong> — A previously offline node has started heartbeating again.</li>
        <li><strong>Camera offline</strong> — A camera on an online node stopped reporting segments (cable unplugged, USB error, camera held open by another app).</li>
        <li><strong>Motion detected</strong> — A camera's FFmpeg scene-change scorer crossed the configured threshold. See <a href="#motion-detection">Motion Detection</a>.</li>
        <li><strong>Incident opened</strong> — A human or MCP agent filed a new incident report.</li>
      </ul>

      <h3>Where they show up</h3>
      <ul>
        <li><strong>In-app banners</strong> — Non-blocking toasts at the top of the dashboard while you're signed in.</li>
        <li><strong>Incidents tab</strong> — Any notification filed as an incident appears there for triage.</li>
        <li><strong>MCP tool log</strong> — Admin dashboard shows every MCP call, including ones that fired on a motion event.</li>
      </ul>

      <div className="docs-callout docs-callout-info">
        <p>
          <span className="docs-callout-icon">ℹ️</span>
          <span>Email, SMS, and push-notification delivery are not built into Command
          Center today. If you need external notifications, wire your MCP agent to your
          own notification transport — the agent can call <code>list_cameras</code> +
          <code>view_camera</code> on a motion event and send the result wherever you like.</span>
        </p>
      </div>
    </section>
  )
}

export default Notifications
