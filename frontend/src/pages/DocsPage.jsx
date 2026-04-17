import { useState, useEffect } from "react"
import { Link } from "react-router-dom"
import {
  SystemArchitectureDiagram,
  HlsPipelineDiagram,
  MotionStateMachineDiagram,
  ConfigPrecedenceDiagram,
  IncidentLifecycleDiagram,
  McpWorkflowDiagram,
  SecurityModelDiagram,
  DashboardIaDiagram,
} from "../components/DocsDiagrams"

function DocsPage() {
  const [os, setOs] = useState('linux')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const ua = navigator.userAgent.toLowerCase()
    if (ua.includes('win')) setOs('windows')
    else if (ua.includes('mac')) setOs('macos')
    else setOs('linux')
  }, [])

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const base = window.location.origin
  const installCommands = {
    linux: `curl -fsSL ${base}/install.sh | bash`,
    macos: `curl -fsSL ${base}/install.sh | bash`,
    windows: `irm ${base}/install.ps1 | iex`,
  }

  const OsTabs = ({ id }) => (
    <div className="install-tabs" key={id}>
      <div className="install-tab-buttons">
        {['linux', 'macos', 'windows'].map((o) => (
          <button key={o} className={`install-tab-btn${os === o ? ' active' : ''}`} onClick={() => setOs(o)}>
            {o === 'macos' ? 'macOS' : o.charAt(0).toUpperCase() + o.slice(1)}
          </button>
        ))}
      </div>
      <div className="install-tab-content">
        <div className="docs-code-block">
          <code>{installCommands[os]}</code>
          <button className="docs-copy-btn" onClick={() => copyToClipboard(installCommands[os])}>
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
      </div>
    </div>
  )

  return (
    <div className="docs-layout">
      <aside className="docs-sidebar">
        <div className="docs-sidebar-header">
          <h2>SourceBox Sentry</h2>
          <p>Documentation</p>
        </div>
        <nav className="docs-sidebar-nav">
          <div className="docs-sidebar-group">
            <div className="docs-sidebar-group-label">Introduction</div>
            <a href="#getting-started" className="docs-sidebar-link">Getting Started</a>
            <a href="#architecture" className="docs-sidebar-link">Architecture</a>
          </div>
          <div className="docs-sidebar-group">
            <div className="docs-sidebar-group-label">CloudNode</div>
            <a href="#cloudnode-setup" className="docs-sidebar-link">Setup</a>
            <a href="#configuration" className="docs-sidebar-link">Configuration</a>
            <a href="#deployment" className="docs-sidebar-link">Deployment</a>
            <a href="#motion-detection" className="docs-sidebar-link">Motion Detection</a>
            <a href="#terminal-dashboard" className="docs-sidebar-link">Terminal Dashboard</a>
          </div>
          <div className="docs-sidebar-group">
            <div className="docs-sidebar-group-label">Command Center</div>
            <a href="#dashboard" className="docs-sidebar-link">Dashboard & Features</a>
            <a href="#recording" className="docs-sidebar-link">Recording & Retention</a>
            <a href="#camera-groups" className="docs-sidebar-link">Camera Groups</a>
            <a href="#notifications" className="docs-sidebar-link">Notifications</a>
          </div>
          <div className="docs-sidebar-group">
            <div className="docs-sidebar-group-label">Integrations</div>
            <a href="#mcp" className="docs-sidebar-link">MCP Integration</a>
          </div>
          <div className="docs-sidebar-group">
            <div className="docs-sidebar-group-label">Account & Security</div>
            <a href="#plans" className="docs-sidebar-link">Plans & Limits</a>
            <a href="#security-procedures" className="docs-sidebar-link">Security Procedures</a>
          </div>
          <div className="docs-sidebar-group">
            <div className="docs-sidebar-group-label">Help</div>
            <a href="#troubleshooting" className="docs-sidebar-link">Troubleshooting</a>
            <a href="#faq" className="docs-sidebar-link">FAQ</a>
          </div>
          <div className="docs-sidebar-group">
            <div className="docs-sidebar-group-label">Reference</div>
            <a href="#api-reference" className="docs-sidebar-link">API Reference</a>
          </div>
        </nav>
        <div className="docs-sidebar-footer">
          <Link to="/sign-up" className="docs-sidebar-btn">
            Get Started Free
          </Link>
        </div>
      </aside>

      <main className="docs-content">
        <div className="docs-content-inner">
          <div className="docs-header">
            <h1>Documentation</h1>
            <p>Complete guides for deploying, using, and integrating with SourceBox Sentry.</p>
          </div>

          {/* ── Getting Started ──────────────────────────────── */}
          <section className="docs-section" id="getting-started">
            <h2>Getting Started<a href="#getting-started" className="docs-anchor">#</a></h2>
            <p>
              SourceBox Sentry turns any USB webcam into a cloud-connected security camera without
              router changes, VPNs, or third-party cloud storage in the live video path.
              You bring the camera and a machine to plug it into; we handle streaming,
              storage, access control, and agentic review.
            </p>

            <h3>The two pieces</h3>
            <ul>
              <li><strong>Command Center</strong> — The web dashboard at <code>opensentry-command.fly.dev</code>.
                Lives in the cloud. Hosts your account, cameras, settings, recording
                schedule, audit logs, incident reports, and the MCP endpoint for AI
                assistants. You don't install anything for Command Center — just sign in.</li>
              <li><strong>CloudNode</strong> — A small Rust application you install on a machine
                next to your cameras. It detects USB webcams, encodes their video with
                FFmpeg, and pushes 1-second HLS segments over outbound HTTPS to Command
                Center. It also runs a local terminal dashboard so you can watch what
                it's doing.</li>
            </ul>

            <h3>Core concepts</h3>
            <div className="docs-concepts-grid">
              <div className="docs-concept">
                <h4>Organization</h4>
                <p>A tenant in Command Center. Every camera, node, user, incident, and
                MCP key is scoped to one org. Admins can invite members and manage
                billing; members can view and operate cameras.</p>
              </div>
              <div className="docs-concept">
                <h4>Node</h4>
                <p>A single CloudNode install. A node has a unique <code>node_id</code>, an
                encrypted API key, and one or more cameras. One node per machine is
                the normal deployment.</p>
              </div>
              <div className="docs-concept">
                <h4>Camera</h4>
                <p>A USB webcam discovered by a node. Cameras appear in the dashboard
                automatically when the node comes online and register their codec on
                first segment.</p>
              </div>
              <div className="docs-concept">
                <h4>Segment</h4>
                <p>A <code>.ts</code> HLS video chunk — 1 second by default. CloudNode emits
                a new one every second and pushes it to Command Center, which caches
                roughly 15 at a time per camera in RAM for low-latency playback.</p>
              </div>
              <div className="docs-concept">
                <h4>Incident</h4>
                <p>A structured report file opened by a human or an AI agent. Holds a
                severity, status, markdown write-up, attached snapshots and clips, and
                a timeline of observations. Shows up in the Incidents tab.</p>
              </div>
              <div className="docs-concept">
                <h4>MCP key</h4>
                <p>An API key that authorizes an outside AI client (Claude Code, Cursor,
                custom agents) to call the org's MCP tools. Separate from CloudNode
                API keys. Revocable and auditable.</p>
              </div>
            </div>

            <h3>Prerequisites</h3>
            <ul>
              <li>A USB webcam (built-in laptop cameras work too)</li>
              <li>A SourceBox Sentry account (free tier covers 2 cameras on 1 node)</li>
              <li>A Linux, Windows, or macOS machine for CloudNode</li>
              <li>FFmpeg installed (or Docker) — the installer downloads it automatically on Windows</li>
              <li>Outbound HTTPS access from the CloudNode machine to the internet</li>
            </ul>

            <h3>Quick Setup</h3>
            <div className="docs-steps">
              <div className="docs-step">
                <div className="docs-step-number">1</div>
                <div className="docs-step-content">
                  <h4>Create an account</h4>
                  <p>Visit <code>opensentry-command.fly.dev</code>, sign up, and create your organization. You can invite team members later.</p>
                </div>
              </div>
              <div className="docs-step">
                <div className="docs-step-number">2</div>
                <div className="docs-step-content">
                  <h4>Create a node and get your API key</h4>
                  <p>Go to <strong>Settings</strong>, click <strong>Add Node</strong>, name it, and copy the API key. Save it — you won't see it again.</p>
                </div>
              </div>
              <div className="docs-step">
                <div className="docs-step-number">3</div>
                <div className="docs-step-content">
                  <h4>Install CloudNode</h4>
                  <OsTabs id="qs" />
                  <p>The installer downloads CloudNode, checks for FFmpeg, and walks you through setup.</p>
                </div>
              </div>
              <div className="docs-step">
                <div className="docs-step-number">4</div>
                <div className="docs-step-content">
                  <h4>View your camera</h4>
                  <p>Once CloudNode is running, your camera appears on the dashboard automatically. Click it to watch the live HLS stream.</p>
                </div>
              </div>
            </div>

            <div className="docs-callout docs-callout-info">
              <p>
                <span className="docs-callout-icon">ℹ️</span>
                <span>CloudNode only makes <strong>outbound</strong> HTTPS connections. No inbound ports, no port forwarding, no VPN required.</span>
              </p>
            </div>
          </section>

          {/* ── CloudNode Setup ──────────────────────────────── */}
          <section className="docs-section" id="cloudnode-setup">
            <h2>CloudNode Setup<a href="#cloudnode-setup" className="docs-anchor">#</a></h2>
            <p>
              CloudNode is a Rust application that captures video from USB cameras,
              encodes it as HLS segments with FFmpeg, and pushes them to the Command Center
              backend, which serves them to viewers from an in-memory cache.
            </p>

            <h3>Installation</h3>
            <OsTabs id="cn" />
            <p style={{ marginTop: '0.75rem', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
              {os === 'windows' ? 'Run in PowerShell as Administrator.' : 'Run in your terminal.'}
            </p>

            <h3>Setup Wizard</h3>
            <p>After installation, configure your API key:</p>
            <div className="docs-code-block">
              <code>{os === 'windows' ? 'opensentry-cloudnode.exe setup' : 'opensentry-cloudnode setup'}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(os === 'windows' ? 'opensentry-cloudnode.exe setup' : 'opensentry-cloudnode setup')}>Copy</button>
            </div>

            <h3>Configuration</h3>
            <p>
              CloudNode stores all configuration in a local SQLite database (<code>data/node.db</code>).
              The API key is encrypted at rest. Key settings:
            </p>
            <ul>
              <li><code>node_id</code> — Unique identifier assigned by Command Center</li>
              <li><code>api_key</code> — Authentication key (encrypted at rest)</li>
              <li><code>api_url</code> — Command Center URL</li>
              <li><code>encoder</code> — Hardware encoder auto-detected: NVENC, QSV, AMF, or falls back to libx264</li>
            </ul>

            <h3>Running</h3>
            <div className="docs-code-block">
              <code>{os === 'windows' ? '.\\opensentry-cloudnode.exe' : './opensentry-cloudnode'}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(os === 'windows' ? '.\\opensentry-cloudnode.exe' : './opensentry-cloudnode')}>Copy</button>
            </div>
            <p>CloudNode auto-detects connected USB cameras and starts streaming immediately.</p>

            <h3>What CloudNode Does</h3>
            <ul>
              <li>Discovers USB cameras and registers them with Command Center</li>
              <li>Captures video and encodes HLS segments (1-second chunks by default) via FFmpeg</li>
              <li>Pushes segments directly to the Command Center backend over authenticated HTTPS</li>
              <li>Sends heartbeats every 30 seconds to report camera status</li>
              <li>Auto-detects video/audio codecs and reports them to Command Center</li>
              <li>Supports hardware-accelerated encoding on NVIDIA, Intel, and AMD GPUs</li>
              <li>Stores recordings and snapshots locally in an encrypted SQLite database</li>
              <li>Runs a live terminal dashboard with slash commands and log viewer</li>
            </ul>
          </section>

          {/* ── Configuration ─────────────────────────────────── */}
          <section className="docs-section" id="configuration">
            <h2>Configuration<a href="#configuration" className="docs-anchor">#</a></h2>
            <p>
              CloudNode resolves configuration from multiple sources so you can run it
              however suits your deployment — interactive wizard for a single box,
              environment variables for Docker, CLI flags for one-off overrides.
            </p>

            <h3>Loading order</h3>
            <p>Higher priority overrides lower priority:</p>
            <ol>
              <li><strong>SQLite database</strong> (<code>data/node.db</code>) — primary source of truth, written by the setup wizard and encrypted at rest</li>
              <li><strong>YAML file</strong> (<code>config.yaml</code>) — legacy fallback, auto-migrated into the DB on first load</li>
              <li><strong>Environment variables</strong> — override any stored value at runtime</li>
              <li><strong>CLI flags</strong> — highest priority, typically used for debugging</li>
            </ol>
            <ConfigPrecedenceDiagram />

            <h3>Environment variables</h3>
            <div className="docs-plans-table">
              <table>
                <thead>
                  <tr><th>Variable</th><th>Purpose</th></tr>
                </thead>
                <tbody>
                  <tr><td><code>OPENSENTRY_NODE_ID</code></td><td>Node ID assigned by Command Center</td></tr>
                  <tr><td><code>OPENSENTRY_API_KEY</code></td><td>Node API key (encrypted at rest in the DB)</td></tr>
                  <tr><td><code>OPENSENTRY_API_URL</code></td><td>Command Center URL (<code>https://opensentry-command.fly.dev</code>)</td></tr>
                  <tr><td><code>OPENSENTRY_ENCODER</code></td><td>Force a specific encoder (e.g. <code>h264_nvenc</code>, <code>libx264</code>)</td></tr>
                  <tr><td><code>RUST_LOG</code></td><td>Log verbosity: <code>trace</code>, <code>debug</code>, <code>info</code>, <code>warn</code>, <code>error</code></td></tr>
                </tbody>
              </table>
            </div>

            <h3>CLI flags</h3>
            <p>
              For one-off runs you can pass the three core values on the command line.
              They override anything in the database and env:
            </p>
            <div className="docs-code-block">
              <code>opensentry-cloudnode --node-id NODE --api-key KEY --api-url URL</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard('opensentry-cloudnode --node-id NODE --api-key KEY --api-url URL')}>Copy</button>
            </div>

            <h3>Example <code>config.yaml</code></h3>
            <p>
              The YAML file is optional — only needed if you want to seed values without the
              wizard, or tune motion detection. Placed next to the binary:
            </p>
            <div className="docs-code-block">
              <code>{`node_id: "node_abc123"
api_key: "nak_your_key_here"
api_url: "https://opensentry-command.fly.dev"

motion:
  enabled: true
  threshold: 0.02      # 0.0 = identical, 1.0 = totally different
  cooldown_secs: 30    # minimum seconds between motion events per camera

storage:
  max_size_gb: 20      # oldest recordings/snapshots evicted when over`}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(`node_id: "node_abc123"
api_key: "nak_your_key_here"
api_url: "https://opensentry-command.fly.dev"

motion:
  enabled: true
  threshold: 0.02
  cooldown_secs: 30

storage:
  max_size_gb: 20`)}>Copy</button>
            </div>

            <h3>Credential storage</h3>
            <p>
              The node API key is encrypted at rest in the SQLite DB using AES-256-GCM
              with a machine-derived key (SHA-256 of hostname + application salt). The
              database is <strong>not portable</strong> — copying <code>node.db</code> to a
              different host will make the stored key unreadable. Re-run <code>setup</code>
              after moving to a new machine.
            </p>

            <h3>Resetting a node</h3>
            <ul>
              <li><strong><code>/reauth confirm</code></strong> — from the dashboard's settings page, clears credentials and reopens the setup wizard. Preserves recordings.</li>
              <li><strong><code>/wipe confirm</code></strong> — erases all stored data (credentials, recordings, snapshots) and restarts setup from scratch.</li>
            </ul>
          </section>

          {/* ── Deployment ────────────────────────────────────── */}
          <section className="docs-section" id="deployment">
            <h2>Deployment<a href="#deployment" className="docs-anchor">#</a></h2>
            <p>
              Three ways to run CloudNode in production. Pick the one that matches your
              existing ops setup.
            </p>

            <h3>Docker (single camera)</h3>
            <p>The most portable option. Maps one USB camera device into the container:</p>
            <div className="docs-code-block">
              <code>{`docker build -t opensentry-cloudnode .

docker run -d \\
  --name opensentry-cloudnode \\
  --device /dev/video0:/dev/video0 \\
  -e OPENSENTRY_NODE_ID=your_node_id \\
  -e OPENSENTRY_API_KEY=your_api_key \\
  -e OPENSENTRY_API_URL=https://opensentry-command.fly.dev \\
  -p 8080:8080 \\
  -v ./data:/app/data \\
  opensentry-cloudnode`}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(`docker run -d \\
  --name opensentry-cloudnode \\
  --device /dev/video0:/dev/video0 \\
  -e OPENSENTRY_NODE_ID=your_node_id \\
  -e OPENSENTRY_API_KEY=your_api_key \\
  -e OPENSENTRY_API_URL=https://opensentry-command.fly.dev \\
  -p 8080:8080 \\
  -v ./data:/app/data \\
  opensentry-cloudnode`)}>Copy</button>
            </div>

            <h3>Docker (multiple cameras)</h3>
            <p>Pass each <code>/dev/video*</code> device explicitly:</p>
            <div className="docs-code-block">
              <code>{`docker run -d \\
  --device /dev/video0:/dev/video0 \\
  --device /dev/video2:/dev/video2 \\
  -e OPENSENTRY_NODE_ID=your_node_id \\
  -e OPENSENTRY_API_KEY=your_api_key \\
  -e OPENSENTRY_API_URL=https://opensentry-command.fly.dev \\
  -p 8080:8080 \\
  opensentry-cloudnode`}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(`docker run -d \\
  --device /dev/video0:/dev/video0 \\
  --device /dev/video2:/dev/video2 \\
  -e OPENSENTRY_NODE_ID=your_node_id \\
  -e OPENSENTRY_API_KEY=your_api_key \\
  -e OPENSENTRY_API_URL=https://opensentry-command.fly.dev \\
  -p 8080:8080 \\
  opensentry-cloudnode`)}>Copy</button>
            </div>

            <h3>Docker Compose</h3>
            <p>For declarative config, use the included <code>docker-compose.yml</code>:</p>
            <div className="docs-code-block">
              <code>{`cp .env.example .env
# Edit .env with your credentials
docker-compose up -d`}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(`cp .env.example .env
# Edit .env with your credentials
docker-compose up -d`)}>Copy</button>
            </div>

            <h3>Build from source</h3>
            <p>If you prefer native install — Rust 1.70+ and FFmpeg must already be on the box:</p>
            <div className="docs-code-block">
              <code>{`git clone https://github.com/SourceBox-LLC/opensentry-cloud-node.git
cd opensentry-cloud-node
cargo build --release
./target/release/opensentry-cloudnode setup`}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(`git clone https://github.com/SourceBox-LLC/opensentry-cloud-node.git
cd opensentry-cloud-node
cargo build --release
./target/release/opensentry-cloudnode setup`)}>Copy</button>
            </div>

            <h3>systemd service (Linux)</h3>
            <p>To run CloudNode as a background service on boot, create <code>/etc/systemd/system/opensentry-cloudnode.service</code>:</p>
            <div className="docs-code-block">
              <code>{`[Unit]
Description=SourceBox Sentry CloudNode
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=opensentry
WorkingDirectory=/opt/opensentry
ExecStart=/opt/opensentry/opensentry-cloudnode
Restart=on-failure
RestartSec=5
Environment=RUST_LOG=info

[Install]
WantedBy=multi-user.target`}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(`[Unit]
Description=SourceBox Sentry CloudNode
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=opensentry
WorkingDirectory=/opt/opensentry
ExecStart=/opt/opensentry/opensentry-cloudnode
Restart=on-failure
RestartSec=5
Environment=RUST_LOG=info

[Install]
WantedBy=multi-user.target`)}>Copy</button>
            </div>
            <p>Enable and start:</p>
            <div className="docs-code-block">
              <code>sudo systemctl enable --now opensentry-cloudnode</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard('sudo systemctl enable --now opensentry-cloudnode')}>Copy</button>
            </div>

            <h3>Cross-compilation (Raspberry Pi)</h3>
            <p>CloudNode runs on ARM64 Linux — build on a dev machine, copy the binary:</p>
            <div className="docs-code-block">
              <code>{`rustup target add aarch64-unknown-linux-gnu
cargo build --release --target aarch64-unknown-linux-gnu`}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(`rustup target add aarch64-unknown-linux-gnu
cargo build --release --target aarch64-unknown-linux-gnu`)}>Copy</button>
            </div>

            <h3>Updating</h3>
            <p>
              Re-run the install script. It downloads the latest release, preserves your
              <code>data/node.db</code>, and restarts the binary. With Docker, pull the new image
              and recreate the container. With systemd, replace the binary and run
              <code>sudo systemctl restart opensentry-cloudnode</code>.
            </p>
          </section>

          {/* ── Motion Detection ──────────────────────────────── */}
          <section className="docs-section" id="motion-detection">
            <h2>Motion Detection<a href="#motion-detection" className="docs-anchor">#</a></h2>
            <p>
              Motion detection is built into CloudNode — no extra service, no external API
              calls. Every camera runs a second FFmpeg process in parallel that scores how
              much each frame differs from the previous one; above-threshold frames fire a
              <code>motion_detected</code> event.
            </p>

            <h3>How it works</h3>
            <ol>
              <li>A lightweight FFmpeg probe runs alongside the HLS encoder for each camera</li>
              <li>It uses the <code>select='gt(scene,THRESHOLD)'</code> filter to emit a scene-change score per frame, between 0.0 (identical) and 1.0 (totally different)</li>
              <li>When a frame's score crosses your threshold, CloudNode raises a <code>MotionEvent</code></li>
              <li>The event is sent over the persistent WebSocket to Command Center. If the socket is down, it falls back to <code>POST /api/cameras/{"{id}"}/motion</code></li>
              <li>A per-camera cooldown timer prevents flapping (identical wind-blown tree, flickering light) from spamming events</li>
            </ol>
            <MotionStateMachineDiagram />

            <h3>Configuration</h3>
            <div className="docs-plans-table">
              <table>
                <thead>
                  <tr><th>Field</th><th>Default</th><th>Meaning</th></tr>
                </thead>
                <tbody>
                  <tr><td><code>motion.enabled</code></td><td><code>true</code></td><td>Toggle motion detection on/off</td></tr>
                  <tr><td><code>motion.threshold</code></td><td><code>0.02</code></td><td>Scene-change score threshold. Lower = more sensitive.</td></tr>
                  <tr><td><code>motion.cooldown_secs</code></td><td><code>30</code></td><td>Minimum seconds between events per camera</td></tr>
                </tbody>
              </table>
            </div>

            <h3>Tuning the threshold</h3>
            <ul>
              <li><strong>0.01–0.02 (default)</strong> — general-purpose indoor rooms and porches. Catches a person walking through frame.</li>
              <li><strong>0.03–0.05</strong> — outdoor scenes with wind or foliage. Ignores minor sway.</li>
              <li><strong>0.001–0.005</strong> — dim scenes with low contrast. Detects subtle changes — at the cost of noisier events.</li>
            </ul>
            <p>
              Watch the dashboard log — it prints <code>Motion detected on CAMERA (score N%)</code>
              every time an event fires. If you're getting too many, raise the threshold.
              Getting none when something clearly moved? Lower it.
            </p>

            <h3>Event payload</h3>
            <p>The event sent over WebSocket (or HTTP fallback) looks like:</p>
            <div className="docs-code-block">
              <code>{`{
  "command": "motion_detected",
  "camera_id": "cam_abc123",
  "score": 0.043,
  "timestamp": "2026-04-13T14:23:11Z"
}`}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(`{
  "command": "motion_detected",
  "camera_id": "cam_abc123",
  "score": 0.043,
  "timestamp": "2026-04-13T14:23:11Z"
}`)}>Copy</button>
            </div>

            <div className="docs-callout docs-callout-info">
              <p>
                <span className="docs-callout-icon">💡</span>
                <span>Motion events are the signal AI agents use to prioritize which camera
                to check first. Hook them into <code>create_incident</code> via MCP to auto-open
                incidents when motion fires in off-hours.</span>
              </p>
            </div>
          </section>

          {/* ── Terminal Dashboard ────────────────────────────── */}
          <section className="docs-section" id="terminal-dashboard">
            <h2>Terminal Dashboard<a href="#terminal-dashboard" className="docs-anchor">#</a></h2>
            <p>
              CloudNode runs a full-screen terminal dashboard while streaming. It shows
              camera status, upload progress, and live logs — and lets you drive the node
              with slash commands without restarting the process.
            </p>

            <h3>Main view</h3>
            <p>Type <code>/</code> and press <strong>Enter</strong> to open the command menu.</p>
            <div className="docs-plans-table">
              <table>
                <thead>
                  <tr><th>Command</th><th>What it does</th></tr>
                </thead>
                <tbody>
                  <tr><td><code>/settings</code></td><td>Open the settings page</td></tr>
                  <tr><td><code>/status</code></td><td>Show a short status summary (cameras, uptime, last upload)</td></tr>
                  <tr><td><code>/clear</code></td><td>Clear the log panel</td></tr>
                  <tr><td><code>/quit</code></td><td>Stop the node and exit gracefully</td></tr>
                </tbody>
              </table>
            </div>

            <h3>Settings page</h3>
            <p>From the settings page, additional commands are available:</p>
            <div className="docs-plans-table">
              <table>
                <thead>
                  <tr><th>Command</th><th>What it does</th></tr>
                </thead>
                <tbody>
                  <tr><td><code>/export-logs</code></td><td>Save the full log buffer to a timestamped file</td></tr>
                  <tr><td><code>/wipe confirm</code></td><td>Erase all stored data and restart setup</td></tr>
                  <tr><td><code>/reauth confirm</code></td><td>Clear credentials and re-run the setup wizard</td></tr>
                  <tr><td><code>/back</code></td><td>Return to the dashboard</td></tr>
                </tbody>
              </table>
            </div>
            <p>Press <strong>Esc</strong> at any time to go back. Destructive commands require the <code>confirm</code> argument to fire — typing <code>/wipe</code> alone does nothing.</p>

            <h3>Log levels</h3>
            <p>The dashboard respects <code>RUST_LOG</code>. Set it before starting to see more or less detail:</p>
            <div className="docs-code-block">
              <code>RUST_LOG=debug ./opensentry-cloudnode</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard('RUST_LOG=debug ./opensentry-cloudnode')}>Copy</button>
            </div>
          </section>

          {/* ── Dashboard & Features ──────────────────────────── */}
          <section className="docs-section" id="dashboard">
            <h2>Dashboard & Features<a href="#dashboard" className="docs-anchor">#</a></h2>
            <p>The Command Center web dashboard is where your team actually uses the system. It's organized into a few main areas.</p>

            <DashboardIaDiagram />

            <h3>Live view</h3>
            <p>
              The default page after sign-in. Every camera appears as a tile with a status
              pill (online, offline, or stale) and a live HLS player you can expand. Tiles
              are grouped by camera group and each tile shows its node name for quick
              identification.
            </p>
            <ul>
              <li><strong>Live Streams</strong> — HLS video served same-origin through the Command Center proxy, JWT-authenticated per viewer. Starts at the live edge.</li>
              <li><strong>Snapshots</strong> — Click the camera icon to capture a single JPEG and save it on the node. Shows up in the node's snapshots list.</li>
              <li><strong>Recording</strong> — Manual start/stop per camera. Recordings are stored locally on the node in the encrypted SQLite database.</li>
              <li><strong>Fullscreen + multi-view</strong> — Click a tile to expand to full screen, or select multiple tiles to watch side-by-side.</li>
            </ul>

            <h3>Settings</h3>
            <p>Configure your org, nodes, and recording policy. Admin-only.</p>
            <ul>
              <li><strong>Node Management</strong> — Create nodes, copy API keys at creation time, rotate keys, delete nodes (cascades to cameras).</li>
              <li><strong>Recording Settings</strong> — Toggle continuous 24/7 or scheduled recording and define the time window. See the <a href="#recording">Recording</a> section below.</li>
              <li><strong>Organization</strong> — Invite members, manage roles (Admin vs Member), view resource usage relative to plan caps.</li>
              <li><strong>Subscription</strong> — Current plan, usage bars for cameras and nodes, and an upgrade/downgrade flow.</li>
              <li><strong>Danger Zone</strong> — Wipe stream logs or perform a full organization reset. Pro/Business only and each action requires a typed confirmation.</li>
            </ul>

            <h3>Admin dashboard</h3>
            <p>Pro and Business plans unlock a separate Admin dashboard for auditing and analytics:</p>
            <ul>
              <li><strong>Stream Access Logs</strong> — Who watched which camera, from which IP, at what time. One row per user × camera × ~5-minute window.</li>
              <li><strong>Usage Statistics</strong> — Views by camera, by user, and by day. Useful to see which feeds matter and which are dormant.</li>
              <li><strong>MCP Tool Activity</strong> — Every tool call made by a connected AI client: which key, which tool, what it did, whether it succeeded.</li>
              <li><strong>System Health</strong> — Online vs offline camera counts, node heartbeat ages, segment cache status.</li>
            </ul>

            <h3>AI incident reports</h3>
            <p>
              When an AI client is connected over MCP, it can open structured incident reports
              on your behalf. Each report has a severity, status, markdown write-up, attached
              snapshots, video clips, and a timeline of observations — all editable from the
              Incidents tab in the dashboard.
            </p>
            <IncidentLifecycleDiagram />
            <ul>
              <li><strong>Create</strong> — Agents open an incident when they notice something worth
                flagging (possible intruder, equipment fault, unexpected motion).</li>
              <li><strong>Investigate</strong> — They can attach fresh JPEG snapshots from any camera,
                save short video clips from a camera's recent live buffer, and log text observations
                as they check other feeds.</li>
              <li><strong>Finalize</strong> — A markdown report is written at the end with what was
                seen, what was ruled out, and any recommended actions.</li>
              <li><strong>Review</strong> — Humans open the Incidents tab, read the report, view the
                evidence thumbnails, play back the captured clips, and mark each incident
                acknowledged, resolved, or dismissed.</li>
              <li><strong>Look back</strong> — Agents can also list and re-read past incidents
                (including fetching their snapshots and clip metadata) so they can follow up without
                losing context.</li>
            </ul>
            <p className="docs-subtle">
              Requires MCP access (Pro or Business) and an MCP API key. See
              the <a href="#mcp">MCP Integration</a> section for setup.
            </p>
          </section>

          {/* ── Recording & Retention ─────────────────────────── */}
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

          {/* ── Camera Groups ─────────────────────────────────── */}
          <section className="docs-section" id="camera-groups">
            <h2>Camera Groups<a href="#camera-groups" className="docs-anchor">#</a></h2>
            <p>
              Camera groups are user-defined zones — "Front yard", "Workshop", "Main floor" —
              that bundle cameras together for filtering, display, and MCP agent navigation.
            </p>

            <h3>Creating a group</h3>
            <ol>
              <li>Open <Link to="/settings">Settings</Link> &gt; Camera Groups</li>
              <li>Click <strong>New Group</strong>, give it a name and a color</li>
              <li>Drag cameras into the group, or assign a group from the camera's settings drawer</li>
            </ol>

            <h3>What groups do for you</h3>
            <ul>
              <li><strong>Live view layout</strong> — The dashboard tile grid is grouped by camera group, so related cameras stay adjacent.</li>
              <li><strong>Color tagging</strong> — Each group has a color. Tiles and tile borders reflect it so you can read a 20-camera grid at a glance.</li>
              <li><strong>Filter and search</strong> — Filter the live view or access logs by group name.</li>
              <li><strong>MCP navigation</strong> — Agents call <code>list_camera_groups</code> to resolve a natural-language location ("check the workshop") to a set of <code>camera_id</code>s.</li>
            </ul>

            <h3>Tips</h3>
            <ul>
              <li>Name groups by <em>place</em>, not purpose. "Driveway" stays meaningful as cameras come and go; "Vehicle monitoring" doesn't.</li>
              <li>Use a color system your team recognizes — e.g. red for perimeter, blue for interior, green for delivery zones.</li>
              <li>A camera can only be in one group. If you need multi-group overlap, duplicate the camera tile in a saved view instead (planned feature).</li>
            </ul>
          </section>

          {/* ── Notifications ─────────────────────────────────── */}
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

          {/* ── MCP Integration ──────────────────────────────── */}
          <section className="docs-section" id="mcp">
            <h2>MCP Integration<a href="#mcp" className="docs-anchor">#</a></h2>
            <div className="docs-callout docs-callout-info">
              <p>
                <span className="docs-callout-icon">✨</span>
                <span>MCP integration requires a <strong>Pro</strong> or <strong>Business</strong> plan.</span>
              </p>
            </div>
            <p>
              SourceBox Sentry supports the <strong>Model Context Protocol (MCP)</strong>, letting AI tools like
              Claude Code, Cursor, or custom agents interact with your cameras, nodes, and settings
              through natural language.
            </p>

            <h3>What is MCP?</h3>
            <p>
              MCP is an open protocol that lets AI assistants connect to external tools and data sources.
              When you connect an AI tool to SourceBox Sentry via MCP, it can list your cameras, check node
              status, get stream URLs, manage recording settings, and more — all through conversation.
            </p>

            <h3>Agent workflow</h3>
            <p>
              A typical agent session flows through three lanes. The agent drives the
              conversation and calls MCP tools; Command Center authenticates each call
              and routes it; CloudNode produces physical data (JPEGs, clip bytes)
              whenever a tool needs a live view of a camera.
            </p>
            <McpWorkflowDiagram />

            <h3>Setup</h3>
            <div className="docs-steps">
              <div className="docs-step">
                <div className="docs-step-number">1</div>
                <div className="docs-step-content">
                  <h4>Generate an MCP API key</h4>
                  <p>Go to the <strong>MCP</strong> page in your dashboard and click <strong>Generate Key</strong>. Save it — you won't see it again.</p>
                </div>
              </div>
              <div className="docs-step">
                <div className="docs-step-number">2</div>
                <div className="docs-step-content">
                  <h4>Add to your AI tool</h4>
                  <p>Add the following config to your Claude Code settings (<code>~/.claude.json</code>) or project <code>.mcp.json</code>:</p>
                  <div className="docs-code-block">
                    <code>{`{
  "mcpServers": {
    "opensentry": {
      "type": "http",
      "url": "${base}/mcp",
      "headers": {
        "Authorization": "Bearer osc_your_key_here"
      }
    }
  }
}`}</code>
                    <button className="docs-copy-btn" onClick={() => copyToClipboard(`{
  "mcpServers": {
    "opensentry": {
      "type": "http",
      "url": "${base}/mcp",
      "headers": {
        "Authorization": "Bearer osc_your_key_here"
      }
    }
  }
}`)}>Copy</button>
                  </div>
                  <p>Or via CLI:</p>
                  <div className="docs-code-block">
                    <code>{`claude mcp add --transport http opensentry ${base}/mcp --header "Authorization: Bearer osc_your_key"`}</code>
                    <button className="docs-copy-btn" onClick={() => copyToClipboard(`claude mcp add --transport http opensentry ${base}/mcp --header "Authorization: Bearer osc_your_key"`)}>Copy</button>
                  </div>
                </div>
              </div>
              <div className="docs-step">
                <div className="docs-step-number">3</div>
                <div className="docs-step-content">
                  <h4>Start using it</h4>
                  <p>Ask your AI tool things like "list my cameras" or "get the stream URL for the garage cam".</p>
                </div>
              </div>
            </div>

            <h3>Available Tools</h3>
            <p className="docs-subtle">
              22 tools grouped by capability. VISUAL tools return images the model can look at,
              READ tools return structured data, and WRITE tools create or update state.
            </p>

            <h4>Live viewing</h4>
            <div className="docs-mcp-tools">
              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">VISUAL</span>
                <span className="docs-endpoint-path">view_camera</span>
              </div>
              <p>See what a camera sees <em>right now</em> — returns a single live JPEG the agent can actually look at. Use for a one-shot situational check ("is anyone in the workshop?"). For motion or change over time, use <code>watch_camera</code>. To preserve what was seen, follow up with <code>attach_snapshot</code>.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">VISUAL</span>
                <span className="docs-endpoint-path">watch_camera</span>
              </div>
              <p>Burst of 2–10 snapshots from one camera, 1–30s apart. Use when a single <code>view_camera</code> frame isn't enough — to confirm whether a subject is moving, whether motion is sustained or fleeting, or whether something is returning to a scene. For longer evidence retention on an incident, use <code>attach_clip</code>.</p>
            </div>

            <h4>Cameras, nodes &amp; groups</h4>
            <div className="docs-mcp-tools">
              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">list_cameras</span>
              </div>
              <p>Every camera in the org with status, codec, and group assignment. Start here when the agent doesn't yet know what cameras exist — most other camera tools take a <code>camera_id</code> from this output.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_camera</span>
              </div>
              <p>Full metadata for one camera (status, codec, node, group, last seen). Use after <code>list_cameras</code> to inspect one closely. Returns text only — for the actual image, use <code>view_camera</code>.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_stream_url</span>
              </div>
              <p>Returns the authenticated HLS playlist URL for a camera. This is a URL a human or HLS player can open — the agent <em>cannot</em> watch video from it. Use only when handing a stream URL back to the user. To see a frame, use <code>view_camera</code> or <code>watch_camera</code>.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">list_nodes</span>
              </div>
              <p>Every CloudNode (the physical box running cameras on the local network) with status, hostname, and camera count. Use when troubleshooting at the box level — e.g. whether a whole node is offline vs whether one of its cameras is. For per-camera state, use <code>list_cameras</code>.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_node</span>
              </div>
              <p>Full detail for one CloudNode by <code>node_id</code> (hostname, IP, port, status, camera count). Use after <code>list_nodes</code> when you need detail on one specific box — e.g. to confirm which physical device the user should power-cycle.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">list_camera_groups</span>
              </div>
              <p>Camera groups defined in the dashboard — user-defined zones (e.g. "Front yard", "Workshop") that bundle cameras together. Use when the user names a place and you need to find which cameras live there.</p>
            </div>

            <h4>Settings, logs &amp; system</h4>
            <div className="docs-mcp-tools">
              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_recording_settings</span>
              </div>
              <p>The org's recording configuration: whether 24/7 continuous recording is on, whether scheduled recording is on, and the scheduled start/end times. Use when the user asks "are we recording right now?", or before filing an incident if it matters whether the moment was being recorded to disk on the CloudNode.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_stream_logs</span>
              </div>
              <p>Recent stream-access log entries (one row per user × camera × ~5min window). Use to audit who watched a sensitive camera, check whether a user reviewed a feed during a time of interest, or investigate suspicious viewing activity. Filter by <code>camera_id</code> to scope to one feed.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_stream_stats</span>
              </div>
              <p>Aggregated stream-viewing stats over the last N days: totals, by-camera, and by-user. Use to find the most-watched cameras, build a usage summary, or establish a baseline before deciding whether a viewing pattern looks unusual. For per-event detail, use <code>get_stream_logs</code>.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_system_status</span>
              </div>
              <p>High-level snapshot of the org's deployment: camera count with online/offline split, node count with online/offline split, and the active plan. Good first call to orient before drilling in. For per-camera detail, use <code>list_cameras</code>.</p>
            </div>

            <h4>Incident reports</h4>
            <p className="docs-subtle">
              Let the agent file, investigate, and read back structured incident reports.
              Everything written by these tools shows up in the Incidents tab of the dashboard
              for a human to review.
            </p>
            <div className="docs-mcp-tools">
              <div className="docs-endpoint">
                <span className="docs-endpoint-method post">WRITE</span>
                <span className="docs-endpoint-path">create_incident</span>
              </div>
              <p>Open a new incident with a title, summary, severity, and (optionally) a primary camera. Returns the new <code>incident_id</code> to pass to follow-up tools.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method post">WRITE</span>
                <span className="docs-endpoint-path">attach_snapshot</span>
              </div>
              <p>Capture a fresh JPEG from a camera and store it as evidence on an incident. Good for freezing what you saw at the moment of investigation.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method post">WRITE</span>
                <span className="docs-endpoint-path">attach_clip</span>
              </div>
              <p>Save the most recent ~15 seconds of a camera's live buffer as a video clip on an incident. Pulls from the in-memory HLS cache (no recording is started) and stores a single .ts blob the human reviewer can play back from the dashboard.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method post">WRITE</span>
                <span className="docs-endpoint-path">add_observation</span>
              </div>
              <p>Append a free-form text observation (what you checked, what you ruled out) to an incident as you investigate.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method post">WRITE</span>
                <span className="docs-endpoint-path">update_incident</span>
              </div>
              <p>Edit fields on an existing incident: status, severity, short summary, or the long-form markdown report body. Pass only the fields to change. The <code>report</code> parameter REPLACES the existing body, so include the full revised text. Use this for revisions after new evidence — the first report write should go through <code>finalize_incident</code>.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method post">WRITE</span>
                <span className="docs-endpoint-path">finalize_incident</span>
              </div>
              <p>Write the long-form markdown report body for the <em>first</em> time at the end of an investigation, after snapshots/clips and observations are attached. For later revisions, use <code>update_incident</code> with its <code>report</code> parameter instead.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">list_incidents</span>
              </div>
              <p>List previous incidents (most recent first) with optional filters for status, severity, or camera. Skips the full report body — use <code>get_incident</code> for detail.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_incident</span>
              </div>
              <p>Fetch one incident's full detail: summary, markdown report, observations, and evidence metadata (with ids to pass to <code>get_incident_snapshot</code>).</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">VISUAL</span>
                <span className="docs-endpoint-path">get_incident_snapshot</span>
              </div>
              <p>Fetch a snapshot image that was previously attached to an incident as evidence so the agent can actually see what was captured.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_incident_clip</span>
              </div>
              <p>Read metadata about a clip (size, approximate duration, mime, source camera) previously attached with <code>attach_clip</code>. Agents can't watch video, but this confirms the clip is saved and tells the human reviewer what to expect.</p>
            </div>
          </section>

          {/* ── Plans & Limits ────────────────────────────────── */}
          <section className="docs-section" id="plans">
            <h2>Plans & Limits<a href="#plans" className="docs-anchor">#</a></h2>
            <p>SourceBox Sentry offers three plans to fit different needs.</p>

            <div className="docs-plans-table">
              <table>
                <thead>
                  <tr>
                    <th>Feature</th>
                    <th>Free</th>
                    <th>Pro</th>
                    <th>Business</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td>Cameras</td><td>2</td><td>10</td><td>50</td></tr>
                  <tr><td>Nodes</td><td>1</td><td>5</td><td>Unlimited</td></tr>
                  <tr><td>Live Streaming</td><td>Yes</td><td>Yes</td><td>Yes</td></tr>
                  <tr><td>Snapshots</td><td>Yes</td><td>Yes</td><td>Yes</td></tr>
                  <tr><td>Recording</td><td>Yes</td><td>Yes</td><td>Yes</td></tr>
                  <tr><td>Camera Groups</td><td>Yes</td><td>Yes</td><td>Yes</td></tr>
                  <tr><td>Admin Dashboard</td><td>--</td><td>Yes</td><td>Yes</td></tr>
                  <tr><td>Stream Analytics</td><td>--</td><td>Yes</td><td>Yes</td></tr>
                  <tr><td>MCP Integration</td><td>--</td><td>Yes</td><td>Yes</td></tr>
                  <tr><td>MCP Rate Limit</td><td>--</td><td>30 calls/min</td><td>120 calls/min</td></tr>
                  <tr><td>Danger Zone Tools</td><td>--</td><td>Yes</td><td>Yes</td></tr>
                  <tr><td>Priority Support</td><td>--</td><td>--</td><td>Yes</td></tr>
                </tbody>
              </table>
            </div>

            <h3>Enforcement</h3>
            <ul>
              <li><strong>Camera limits</strong> — When a node registers and you're at your camera cap, additional cameras are skipped.</li>
              <li><strong>Node limits</strong> — Creating a node beyond your limit shows an upgrade prompt.</li>
              <li><strong>Feature gates</strong> — Admin dashboard, danger zone, and MCP require Pro or Business.</li>
              <li><strong>MCP rate limits</strong> — Tool calls are rate limited per API key: 30/min on Pro, 120/min on Business. Exceeding the limit returns an error until the window resets.</li>
            </ul>

            <p>Manage your subscription from <strong>Settings &gt; Subscription</strong> or the <Link to="/pricing">Pricing</Link> page.</p>
          </section>

          {/* ── Architecture ──────────────────────────────────── */}
          <section className="docs-section" id="architecture">
            <h2>Architecture<a href="#architecture" className="docs-anchor">#</a></h2>
            <p>SourceBox Sentry uses a cloud-first architecture designed for simplicity and security.</p>

            <h3>Data Flow</h3>
            <SystemArchitectureDiagram />

            <h3>How It Works</h3>
            <ol>
              <li><strong>CloudNode</strong> captures video from USB cameras using FFmpeg</li>
              <li>Video is encoded as HLS segments (1-second chunks by default) and pushed directly to the Command Center over authenticated HTTPS</li>
              <li>The <strong>Command Center</strong> caches the most recent segments in RAM and serves them to authorized viewers same-origin</li>
              <li>Viewers watch via HLS through the Command Center backend — no third-party storage in the live video path, no direct connection to your network</li>
            </ol>

            <h3>HLS Segment Pipeline</h3>
            <p>
              Zooming into the streaming path: each camera runs two FFmpeg processes
              in parallel — one producing playable HLS segments, a second probing
              scene changes for motion events. Playback is served same-origin from
              the backend's RAM cache, never through object storage.
            </p>
            <HlsPipelineDiagram />

            <h3>Security Model</h3>
            <p>
              Every request crosses four layers of protection. TLS on the wire, an
              authenticated identity at the edge, hashing or encryption wherever
              data is stored, and tenant isolation all the way down to the database
              query.
            </p>
            <SecurityModelDiagram />
            <ul>
              <li><strong>Outbound Only</strong> — CloudNode pushes to cloud. No inbound ports, no router config.</li>
              <li><strong>Same-origin Streaming</strong> — Live segments are served through the authenticated backend, not a third-party object store.</li>
              <li><strong>API Key Auth</strong> — Node keys stored as SHA-256 hashes. Never stored in plaintext.</li>
              <li><strong>Clerk Organizations</strong> — Multi-tenant auth with admin and member roles.</li>
              <li><strong>HTTPS Everywhere</strong> — All traffic between CloudNode, Command Center, and viewers is encrypted.</li>
              <li><strong>MCP Keys</strong> — Separate API keys for MCP access, also SHA-256 hashed and org-scoped.</li>
            </ul>
          </section>

          {/* ── Security Procedures ─────────────────────────────── */}
          <section className="docs-section" id="security-procedures">
            <h2>Security Procedures<a href="#security-procedures" className="docs-anchor">#</a></h2>
            <p>Step-by-step guides for handling security incidents. Act quickly to minimize exposure.</p>

            <h3>Compromised MCP API Key</h3>
            <p>If you suspect an MCP API key has been leaked, shared, or used by an unauthorized party:</p>
            <ol>
              <li><strong>Revoke the key immediately</strong> — Go to the <Link to="/mcp">MCP Control Center</Link>, find the key, and click <strong>Revoke</strong>. This takes effect instantly.</li>
              <li><strong>Review MCP activity logs</strong> — Go to <Link to="/admin">Admin Dashboard</Link> and check the <strong>MCP Tool Activity</strong> section. Filter by the compromised key name to see exactly which tools were called, when, and what data was accessed.</li>
              <li><strong>Generate a new key</strong> — Create a replacement key in the MCP Control Center and update your AI client configuration.</li>
              <li><strong>Check for unusual access</strong> — Look for unexpected <code>view_camera</code> or <code>watch_camera</code> calls that may indicate someone was viewing your camera feeds.</li>
            </ol>

            <h3>Compromised CloudNode API Key</h3>
            <p>If a CloudNode API key is compromised, an attacker could potentially push video segments to your storage:</p>
            <ol>
              <li><strong>Rotate the key</strong> — Go to <Link to="/settings">Settings</Link>, find the node, and click <strong>Rotate Key</strong>. The old key is invalidated immediately.</li>
              <li><strong>Update the CloudNode</strong> — The CloudNode will disconnect. Re-run setup with the new API key.</li>
              <li><strong>Review audit logs</strong> — Check stream access logs in the <Link to="/admin">Admin Dashboard</Link> for unusual activity.</li>
              <li><strong>Verify video integrity</strong> — If you suspect tamppered footage, check your CloudNode logs for upload activity you don't recognize.</li>
            </ol>

            <h3>Compromised User Account</h3>
            <p>If a Clerk user account in your organization is compromised:</p>
            <ol>
              <li><strong>Remove the user</strong> — Go to your Clerk dashboard and remove the user from the organization or disable their account.</li>
              <li><strong>Revoke all MCP keys</strong> — If the user had admin access, they may have created MCP API keys. Revoke all keys in the <Link to="/mcp">MCP Control Center</Link> and regenerate only the ones you need.</li>
              <li><strong>Rotate CloudNode keys</strong> — If the user had <code>manage_cameras</code> permission, rotate all node API keys from <Link to="/settings">Settings</Link>.</li>
              <li><strong>Review all logs</strong> — Check both stream access logs and MCP activity logs in the <Link to="/admin">Admin Dashboard</Link> for the affected time period.</li>
            </ol>

            <h3>Suspicious Camera Access</h3>
            <p>If you see unexpected entries in your stream access logs:</p>
            <ol>
              <li><strong>Identify the source</strong> — Check the user email, IP address, and timestamp in <Link to="/admin">Admin Dashboard</Link> &gt; Stream Access Logs.</li>
              <li><strong>Check MCP activity</strong> — If the access came from an MCP tool, the MCP Tool Activity section will show which API key was used.</li>
              <li><strong>Revoke access</strong> — Remove the user from your Clerk organization or revoke the MCP key, depending on the source.</li>
              <li><strong>Enable scheduled recording</strong> — If you don't need 24/7 access, restrict streaming to specific hours from <Link to="/settings">Settings</Link>.</li>
            </ol>

            <h3>General Security Best Practices</h3>
            <ul>
              <li><strong>Rotate keys regularly</strong> — Rotate CloudNode and MCP API keys periodically, even without an incident.</li>
              <li><strong>Use separate MCP keys</strong> — Create a unique MCP API key for each AI client so you can revoke individually.</li>
              <li><strong>Monitor the Admin Dashboard</strong> — Review stream access logs and MCP activity regularly for anything unexpected.</li>
              <li><strong>Keep CloudNode updated</strong> — Always run the latest version for security patches.</li>
              <li><strong>Limit organization members</strong> — Only invite users who need access. Use Clerk roles to restrict permissions.</li>
            </ul>
          </section>

          {/* ── Troubleshooting ───────────────────────────────── */}
          <section className="docs-section" id="troubleshooting">
            <h2>Troubleshooting<a href="#troubleshooting" className="docs-anchor">#</a></h2>
            <p>The most common things that go wrong and how to fix them.</p>

            <h3>No cameras detected</h3>
            <p><strong>Linux:</strong> make sure your user can read video devices:</p>
            <div className="docs-code-block">
              <code>{`ls -l /dev/video*
# Should show crw-rw---- root video

sudo usermod -a -G video $USER
# Log out and back in`}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(`sudo usermod -a -G video $USER`)}>Copy</button>
            </div>
            <p><strong>Windows:</strong> close any other app using the camera (Zoom, Teams, browser tab with <code>getUserMedia</code>). DirectShow only allows one exclusive consumer per camera.</p>
            <p><strong>macOS:</strong> grant camera access in <strong>System Settings &gt; Privacy & Security &gt; Camera</strong> — you'll need to approve the terminal app running CloudNode.</p>

            <h3>FFmpeg not found</h3>
            <p><strong>Windows:</strong> re-run <code>opensentry-cloudnode setup</code>. The wizard downloads a portable FFmpeg into <code>./ffmpeg/bin/</code> if it's missing.</p>
            <p><strong>Linux / macOS:</strong> install via your package manager:</p>
            <div className="docs-code-block">
              <code>{`sudo apt install ffmpeg        # Ubuntu / Debian
sudo dnf install ffmpeg        # Fedora
sudo pacman -S ffmpeg          # Arch
brew install ffmpeg            # macOS`}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard('sudo apt install ffmpeg')}>Copy</button>
            </div>

            <h3>Stream won't play in the dashboard</h3>
            <ol>
              <li>Confirm the node's local server is reachable: <code>curl http://localhost:8080/health</code></li>
              <li>Watch the dashboard log panel for FFmpeg errors (red lines)</li>
              <li>Confirm segments are being created: <code>ls data/hls/&#123;camera_id&#125;/</code> should show new <code>.ts</code> files every second</li>
              <li>Look for <code>Pushed segment …</code> lines — those confirm segments are reaching Command Center</li>
              <li>From settings, run <code>/export-logs</code> and open the file for a full diagnostic</li>
            </ol>

            <h3>Node shows offline in Command Center</h3>
            <p>Command Center marks a node offline if no heartbeat arrives for 90 seconds. Things to check:</p>
            <ul>
              <li>Is the node process actually running? <code>ps aux | grep cloudnode</code> or check the terminal dashboard</li>
              <li>Does outbound HTTPS to <code>opensentry-command.fly.dev</code> work? <code>curl -I https://opensentry-command.fly.dev/api/health</code></li>
              <li>Is the API URL correct in the node config? Open settings via the dashboard <code>/settings</code> command</li>
              <li>Clock skew: if the machine's clock is wildly off, JWT auth may fail. Enable NTP.</li>
              <li>Firewall / egress filter dropping long-lived TLS connections? Test by allowlisting the Fly.io IP and re-running.</li>
            </ul>

            <h3>Segments not appearing in the browser (but node says it's pushing)</h3>
            <ul>
              <li>Refresh the live view — hls.js will retry playlist fetch on reload</li>
              <li>Open browser devtools &gt; Network, filter by <code>.ts</code>, and check for 401/403 errors — that means the viewer's JWT expired. Signing out and back in refreshes it.</li>
              <li>Check the backend logs via Fly: <code>fly logs -a opensentry-command</code></li>
              <li>Confirm the camera is online in <code>list_cameras</code>; if it flipped to offline between the push and the fetch, the cache may have been evicted</li>
            </ul>

            <h3>MCP tool calls return 401</h3>
            <ul>
              <li>Double-check the <code>Authorization: Bearer osc_...</code> header — keys start with the <code>osc_</code> prefix</li>
              <li>Confirm the key is still active in <Link to="/mcp">MCP Control Center</Link></li>
              <li>Your plan must be Pro or Business — Free accounts cannot use MCP</li>
              <li>If you rotated the key, update the AI client config to match</li>
            </ul>

            <h3>MCP tool calls return 429</h3>
            <p>
              You've hit the rate limit (30 calls/min on Pro, 120 calls/min on Business). Wait
              a minute and retry, or upgrade. Rate limits are per API key — splitting an agent
              across multiple keys distributes the budget.
            </p>

            <h3>Hardware encoder won't initialize</h3>
            <p>If CloudNode logs something like <code>h264_nvenc failed, falling back to libx264</code>:</p>
            <ul>
              <li><strong>NVIDIA:</strong> install the NVIDIA driver + <code>nvidia-cuda-toolkit</code>; confirm <code>nvidia-smi</code> works</li>
              <li><strong>Intel QSV:</strong> install <code>intel-media-va-driver</code> (or <code>intel-media-va-driver-non-free</code> for newer CPUs)</li>
              <li><strong>AMD AMF:</strong> only works on Windows with the AMD driver installed</li>
              <li><strong>Force software:</strong> set <code>OPENSENTRY_ENCODER=libx264</code> to skip HW probe entirely</li>
            </ul>

            <h3>High CPU usage</h3>
            <ul>
              <li>The software encoder (<code>libx264</code>) is the biggest cost — install a HW encoder if available</li>
              <li>Motion detection runs a second FFmpeg per camera. If you don't need it, set <code>motion.enabled: false</code></li>
              <li>Reduce camera resolution at the source (most webcams can be set lower via their own driver)</li>
            </ul>

            <h3>Recordings take too much disk</h3>
            <p>Lower <code>storage.max_size_gb</code>. CloudNode will delete the oldest first until it fits. Or switch to scheduled recording instead of continuous.</p>

            <h3>Dashboard logs</h3>
            <p>
              The terminal dashboard has an <code>/export-logs</code> command that writes a
              timestamped file with the full buffer — attach this to any bug report. The
              Command Center side logs to Fly; use <code>fly logs -a opensentry-command</code>
              (requires Fly account access) or ask support.
            </p>
          </section>

          {/* ── FAQ ───────────────────────────────────────────── */}
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
              Not on Free or Pro. Business plan customers get best-effort priority support.
              For enterprise agreements with an SLA, email us via the GitHub org page.
            </p>

            <h3>What license is SourceBox Sentry under?</h3>
            <p>
              Command Center is AGPL-3.0. CloudNode is GPL-3.0. Both are open source — you
              can read, modify, and self-host the code. For commercial licensing that avoids
              the copyleft obligations, contact <a href="https://github.com/SourceBox-LLC" target="_blank" rel="noopener noreferrer">SourceBox LLC</a>.
            </p>
          </section>

          {/* ── API Reference ─────────────────────────────────── */}
          <section className="docs-section" id="api-reference">
            <h2>API Reference<a href="#api-reference" className="docs-anchor">#</a></h2>
            <p>
              Command Center exposes a REST API at <code>{base}</code>. Three
              auth schemes cover three audiences — CloudNode uses API key headers, the web
              dashboard uses Clerk JWTs, and the MCP endpoint uses a dedicated bearer token.
            </p>

            <h3>Authentication</h3>
            <div className="docs-plans-table">
              <table>
                <thead>
                  <tr><th>Scheme</th><th>Header</th><th>Used by</th></tr>
                </thead>
                <tbody>
                  <tr><td>Node API key</td><td><code>X-API-Key: nak_...</code></td><td>CloudNode registering, heartbeating, pushing segments</td></tr>
                  <tr><td>Node API key (alt)</td><td><code>X-Node-API-Key: nak_...</code></td><td>Per-camera endpoints (push-segment, playlist, motion, codec)</td></tr>
                  <tr><td>Clerk JWT</td><td><code>Authorization: Bearer &lt;jwt&gt;</code></td><td>Web dashboard, authenticated viewers</td></tr>
                  <tr><td>MCP key</td><td><code>Authorization: Bearer osc_...</code></td><td>AI clients talking to <code>/mcp</code></td></tr>
                </tbody>
              </table>
            </div>

            <h3>Error format</h3>
            <p>All errors return a JSON body with a stable shape:</p>
            <div className="docs-code-block">
              <code>{`{
  "error": "camera_not_found",
  "message": "No camera with id cam_xyz in this organization",
  "request_id": "req_ab12cd34"
}`}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(`{
  "error": "camera_not_found",
  "message": "No camera with id cam_xyz in this organization",
  "request_id": "req_ab12cd34"
}`)}>Copy</button>
            </div>
            <p>Standard HTTP status codes apply:</p>
            <ul>
              <li><strong>400</strong> — malformed request body or missing required query param</li>
              <li><strong>401</strong> — missing or invalid auth header</li>
              <li><strong>403</strong> — authenticated but not authorized (wrong org, insufficient role, plan gate)</li>
              <li><strong>404</strong> — resource not found in the caller's org</li>
              <li><strong>429</strong> — rate-limit exceeded (MCP only, under Pro/Business budgets)</li>
              <li><strong>5xx</strong> — server error; <code>request_id</code> in the body is what to include in bug reports</li>
            </ul>

            <h3>Example request</h3>
            <p>Listing cameras from a shell with a signed-in user's JWT:</p>
            <div className="docs-code-block">
              <code>{`curl -H "Authorization: Bearer $CLERK_JWT" \\
     ${base}/api/cameras`}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(`curl -H "Authorization: Bearer $CLERK_JWT" ${base}/api/cameras`)}>Copy</button>
            </div>

            <h3>Node Endpoints</h3>
            <p>Used by CloudNode. Authenticate with <code>X-API-Key: {"your_api_key"}</code> header.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/nodes/register</span></div>
            <p>Register a node and its cameras. Returns camera ID mappings.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/nodes/heartbeat</span></div>
            <p>Send periodic heartbeat with camera status updates.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/push-segment</span></div>
            <p>Push a raw HLS <code>.ts</code> segment into the Command Center's in-memory cache. Body is the binary segment, <code>filename</code> is a query param.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/playlist</span></div>
            <p>Push the rolling HLS playlist text. The backend rewrites segment URLs to its own proxy paths and caches the result.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/codec</span></div>
            <p>Report detected video/audio codec information.</p>

            <h3>User Endpoints</h3>
            <p>Used by the web dashboard. Authenticate with Clerk JWT in <code>Authorization: Bearer</code> header.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/cameras</span></div>
            <p>List all cameras in the organization.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/stream.m3u8</span></div>
            <p>Get the cached HLS playlist for browser playback. Segment URLs point at the same-origin segment proxy.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/segment/{"{filename}"}</span></div>
            <p>Serve a single cached HLS segment from memory. JWT-authenticated, same-origin.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/nodes</span></div>
            <p>List all nodes in the organization. Admin only.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/nodes</span></div>
            <p>Create a new node. Returns the API key (shown once).</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/settings</span></div>
            <p>Get recording settings (schedule, continuous mode).</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/audit/stream-logs</span></div>
            <p>Stream access history. Admin only. Filterable by camera and user.</p>

            <h3>Incident Reports</h3>
            <p>
              AI-generated incident reports written by the MCP agent and reviewed by
              admins from the dashboard. All endpoints require admin permission.
            </p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/incidents</span></div>
            <p>List incidents for the org (newest first). Supports <code>status</code>, <code>severity</code>, <code>camera_id</code>, <code>limit</code>, and <code>offset</code> query params.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/incidents/counts</span></div>
            <p>Aggregate counts for the stat bar and badges — total, open, open critical, open high.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/incidents/{"{incident_id}"}</span></div>
            <p>Fetch a single incident with its full markdown report and all evidence metadata.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method patch">PATCH</span><span className="docs-endpoint-path">/api/incidents/{"{incident_id}"}</span></div>
            <p>Acknowledge, resolve, dismiss, or otherwise edit an incident's status, severity, summary, or report.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method delete">DELETE</span><span className="docs-endpoint-path">/api/incidents/{"{incident_id}"}</span></div>
            <p>Permanently delete an incident and all of its evidence (cascades).</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/incidents/{"{incident_id}"}/evidence/{"{evidence_id}"}</span></div>
            <p>Stream a snapshot or clip blob attached as evidence — used by the dashboard to render thumbnails and play back clips in the incident report modal.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/incidents/{"{incident_id}"}/evidence/{"{evidence_id}"}/playlist.m3u8</span></div>
            <p>Synthetic single-segment HLS playlist for a clip evidence item, so the dashboard can reuse hls.js to play back captured video with the same JWT auth as the live player.</p>

            <h3>MCP Endpoint</h3>
            <p>Streamable HTTP transport at <code>/mcp</code>. Authenticate with <code>Authorization: Bearer osc_...</code> header.</p>
            <p>See the <a href="#mcp">MCP Integration</a> section for setup and available tools.</p>
          </section>

          {/* ── Resources ─────────────────────────────────────── */}
          <section className="docs-section">
            <h2>Resources</h2>
            <div className="docs-resources">
              <a href="https://github.com/SourceBox-LLC/OpenSentry-Command" target="_blank" rel="noopener noreferrer" className="docs-resource-card">
                <div className="docs-resource-icon">🖥️</div>
                <h3>Command Center</h3>
                <p>Source code on GitHub</p>
              </a>
              <a href="https://github.com/SourceBox-LLC/opensentry-cloud-node" target="_blank" rel="noopener noreferrer" className="docs-resource-card">
                <div className="docs-resource-icon">📹</div>
                <h3>CloudNode</h3>
                <p>Source code on GitHub</p>
              </a>
              <a href="https://github.com/SourceBox-LLC/OpenSentry-Command/issues" target="_blank" rel="noopener noreferrer" className="docs-resource-card">
                <div className="docs-resource-icon">🐛</div>
                <h3>Report Issue</h3>
                <p>Found a bug? Let us know</p>
              </a>
            </div>
          </section>

          <div className="docs-cta">
            <p>Ready to set up your security camera system?</p>
            <Link to="/sign-up" className="docs-cta-btn">Create Free Account</Link>
          </div>
        </div>
      </main>
    </div>
  )
}

export default DocsPage
