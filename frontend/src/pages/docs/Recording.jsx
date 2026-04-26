import { Link } from "react-router-dom"


function Recording() {
  return (
    <section className="docs-section" id="recording">
      <h2>Recording & Retention<a href="#recording" className="docs-anchor">#</a></h2>
      <p>
        Recording in SourceBox Sentry is <strong>node-local by design</strong>. Command Center
        sends a policy down to every CloudNode; each node writes its own recordings into
        an encrypted SQLite database next to the binary. No video is uploaded for
        long-term storage — the cloud holds only the small in-memory segment buffer
        needed for live playback.
      </p>

      <h3>Recording modes</h3>
      <ul>
        <li><strong>Continuous</strong> — Every camera records 24/7 while its node is online. Best for commercial deployments with plenty of local disk.</li>
        <li><strong>Scheduled</strong> — Recording is on only during a defined time window (e.g. 6pm–6am). Useful for residential after-hours coverage.</li>
        <li><strong>Manual</strong> — Neither continuous nor scheduled is active. Operators trigger recording on-demand from the dashboard.</li>
      </ul>

      <h3>Configure</h3>
      <ol>
        <li>Go to <Link to="/settings">Settings</Link> &gt; Recording</li>
        <li>Pick a mode (<strong>Continuous</strong>, <strong>Scheduled</strong>, or leave off for manual-only)</li>
        <li>For Scheduled, enter the start and end time. Times are in the browser's local timezone, converted to the node's local timezone on delivery.</li>
        <li>Save. Nodes pick up the new setting on their next heartbeat (≤30 seconds).</li>
      </ol>

      <h3>Retention</h3>
      <p>
        CloudNode enforces retention by size, not by age. The <code>storage.max_size_gb</code>
        config field (default <code>20</code>) is a soft cap — when total stored
        recordings + snapshots exceed it, the oldest files are deleted first.
      </p>
      <ul>
        <li>Recordings and snapshots are both stored as BLOBs in the encrypted <code>data/node.db</code></li>
        <li>Retention is checked after every new recording or snapshot</li>
        <li>Adjust the cap to match the disk free on the CloudNode box</li>
      </ul>

      <h3>Playback</h3>
      <p>
        Recordings are browsable from the node's local HTTP server on port 8080 —
        <code>/recordings/list</code> returns the JSON list and <code>/recordings/&#123;file&#125;</code>
        streams the bytes. Typically used from the Command Center dashboard in-app; for
        manual access you must be on the same local network as the node.
      </p>

      <div className="docs-callout docs-callout-info">
        <p>
          <span className="docs-callout-icon">🔒</span>
          <span>Because recordings never leave the node, even a Command Center compromise
          cannot expose your archive. Protect the node machine with the same rigor you'd
          apply to a physical NVR.</span>
        </p>
      </div>
    </section>
  )
}

export default Recording
