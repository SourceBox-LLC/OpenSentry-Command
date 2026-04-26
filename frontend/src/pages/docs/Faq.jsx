function Faq() {
  return (
    <section className="docs-section" id="faq">
      <h2>FAQ<a href="#faq" className="docs-anchor">#</a></h2>

      <h3>Does SourceBox Sentry record audio?</h3>
      <p>
        If a camera's input has audio and its codec is supported (AAC, Opus, MP3),
        CloudNode passes it through the HLS pipeline and it's available during live
        playback. Recordings stored on the node include audio. There is no per-camera
        "mute" toggle yet — remove or mute the input source if you need silent-only.
      </p>

      <h3>Can I use IP cameras (RTSP) instead of USB?</h3>
      <p>
        Not today. CloudNode currently only supports USB cameras via each platform's
        native API (Video4Linux2, DirectShow, AVFoundation). RTSP / ONVIF support is on
        the roadmap — if you have a strong need, open an issue on the CloudNode repo so
        we can prioritize.
      </p>

      <h3>How much bandwidth does a camera use?</h3>
      <p>
        Roughly 1–3 Mbps per 1080p camera at the default encoder settings. Multiply by
        camera count for your egress budget. Local recordings don't add to bandwidth —
        only live viewing via Command Center does.
      </p>

      <h3>Does CloudNode need always-on internet?</h3>
      <p>
        For live streaming to Command Center, yes — segments are pushed as they're
        produced. If the internet drops, the node continues recording locally (if
        recording is enabled) and backfills motion events over the HTTP fallback once
        connectivity returns. Live playback resumes automatically on reconnect.
      </p>

      <h3>Is my video data secure?</h3>
      <ul>
        <li>All traffic between CloudNode, Command Center, and your browser is TLS-encrypted</li>
        <li>Node API keys are stored as SHA-256 hashes server-side and encrypted at rest on the node (AES-256-GCM, machine-derived key)</li>
        <li>Live segments are cached in Command Center RAM for a rolling ~15s window, then evicted — no long-term cloud storage</li>
        <li>Recordings and snapshots live only on your node, in an encrypted SQLite DB</li>
        <li>Every authenticated request is logged for audit</li>
      </ul>

      <h3>Can I self-host Command Center?</h3>
      <p>
        Yes — the Command Center source is available at <a href="https://github.com/SourceBox-LLC/OpenSentry-Command" target="_blank" rel="noopener noreferrer">github.com/SourceBox-LLC/OpenSentry-Command</a>
        under the AGPL-3.0. The project ships a <code>fly.toml</code> for Fly.io deployment
        and a <code>Dockerfile</code> for anywhere else. You'll need your own Clerk
        organization for auth and a Postgres database.
      </p>

      <h3>Which MCP clients does SourceBox Sentry work with?</h3>
      <p>
        Any MCP client that supports the streamable-HTTP transport. Tested with Claude
        Code, Cursor, and custom agents built on Anthropic's Agent SDK. ChatGPT and
        other clients that only support the stdio transport require a local proxy (we
        don't currently document one).
      </p>

      <h3>Can I move a node to a different machine?</h3>
      <p>
        The node database is bound to the host machine (the AES key is derived from
        hostname). To move a node: on the new machine, run <code>opensentry-cloudnode setup</code>
        with the same <code>node_id</code> and API key — Command Center will re-associate
        the cameras to the new host. The old node should be stopped first to avoid a
        split-brain heartbeat.
      </p>

      <h3>How do I reset a node's credentials?</h3>
      <p>
        From the terminal dashboard, go to <code>/settings</code> and run
        <code>/reauth confirm</code>. This clears the stored API key and restarts the
        setup wizard. Use <code>/wipe confirm</code> to additionally delete all
        recordings and snapshots.
      </p>

      <h3>Do you offer an SLA?</h3>
      <p>
        Not on Free or Pro. Pro Plus plan customers get best-effort priority support.
        For enterprise agreements with an SLA, email us via the GitHub org page.
      </p>

      <h3>What license is SourceBox Sentry under?</h3>
      <p>
        Command Center is AGPL-3.0. CloudNode is GPL-3.0. Both are open source — you
        can read, modify, and self-host the code. For commercial licensing that avoids
        the copyleft obligations, contact <a href="https://github.com/SourceBox-LLC" target="_blank" rel="noopener noreferrer">SourceBox LLC</a>.
      </p>
    </section>
  )
}

export default Faq
