import { useState, useEffect } from "react"
import { Link } from "react-router-dom"

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

  const installCommands = {
    linux: 'curl -fsSL https://opensentry-command.fly.dev/install.sh | bash',
    macos: 'curl -fsSL https://opensentry-command.fly.dev/install.sh | bash',
    windows: 'irm https://opensentry-command.fly.dev/install.ps1 | iex',
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
          <h2>OpenSentry</h2>
          <p>Documentation</p>
        </div>
        <nav className="docs-sidebar-nav">
          <a href="#getting-started" className="docs-sidebar-link">Getting Started</a>
          <a href="#cloudnode-setup" className="docs-sidebar-link">CloudNode Setup</a>
          <a href="#dashboard" className="docs-sidebar-link">Dashboard & Features</a>
          <a href="#mcp" className="docs-sidebar-link">MCP Integration</a>
          <a href="#plans" className="docs-sidebar-link">Plans & Limits</a>
          <a href="#architecture" className="docs-sidebar-link">Architecture</a>
          <a href="#api-reference" className="docs-sidebar-link">API Reference</a>
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
            <p>Complete guides for deploying, using, and integrating with OpenSentry.</p>
          </div>

          {/* ── Getting Started ──────────────────────────────── */}
          <section className="docs-section" id="getting-started">
            <h2>Getting Started<a href="#getting-started" className="docs-anchor">#</a></h2>
            <p>
              OpenSentry is a cloud-hosted security camera system with two main components:
            </p>
            <ul>
              <li><strong>Command Center</strong> — Web dashboard hosted on Fly.io for viewing cameras, managing nodes, and controlling settings.</li>
              <li><strong>CloudNode</strong> — Local application that captures video from USB cameras and uploads HLS segments to the cloud.</li>
            </ul>

            <h3>Prerequisites</h3>
            <ul>
              <li>A USB camera connected to your device</li>
              <li>An OpenSentry account (free tier available)</li>
              <li>Windows, Linux, or macOS</li>
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
              encodes it as HLS segments with FFmpeg, and uploads them to Tigris cloud storage
              for global CDN delivery.
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
              <li>Captures video and encodes HLS segments (2-second chunks) via FFmpeg</li>
              <li>Uploads segments to Tigris/S3 with BLAKE3 checksum verification</li>
              <li>Sends heartbeats every 30 seconds to report camera status</li>
              <li>Auto-detects video/audio codecs and reports them to Command Center</li>
              <li>Supports hardware-accelerated encoding on NVIDIA, Intel, and AMD GPUs</li>
            </ul>
          </section>

          {/* ── Dashboard & Features ──────────────────────────── */}
          <section className="docs-section" id="dashboard">
            <h2>Dashboard & Features<a href="#dashboard" className="docs-anchor">#</a></h2>
            <p>The Command Center web dashboard provides everything you need to manage your security system.</p>

            <h3>Dashboard</h3>
            <p>The main view shows all your cameras in a grid with live status indicators.</p>
            <ul>
              <li><strong>Live Streams</strong> — HLS video player for each camera with real-time status</li>
              <li><strong>Snapshots</strong> — Take a snapshot from any camera (saved on the node)</li>
              <li><strong>Recording</strong> — Start/stop recording on individual cameras</li>
              <li><strong>Camera Groups</strong> — Organize cameras by location or purpose with color-coded groups</li>
            </ul>

            <h3>Settings</h3>
            <ul>
              <li><strong>Node Management</strong> — Create nodes, rotate API keys, delete nodes</li>
              <li><strong>Recording Settings</strong> — Enable continuous 24/7 or scheduled recording with time ranges</li>
              <li><strong>Organization</strong> — View org details, member count, and resource usage</li>
              <li><strong>Subscription</strong> — View your current plan, usage bars, and upgrade options</li>
              <li><strong>Danger Zone</strong> — Wipe logs or full organization reset (Pro/Business only)</li>
            </ul>

            <h3>Admin Dashboard</h3>
            <p>Pro and Business plans unlock the Admin dashboard with:</p>
            <ul>
              <li><strong>Stream Access Logs</strong> — See who watched which camera and when</li>
              <li><strong>Usage Statistics</strong> — Views by camera, by user, and by day</li>
              <li><strong>Audit Trail</strong> — Full history of actions taken in your organization</li>
            </ul>
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
              OpenSentry supports the <strong>Model Context Protocol (MCP)</strong>, letting AI tools like
              Claude Code, Cursor, or custom agents interact with your cameras, nodes, and settings
              through natural language.
            </p>

            <h3>What is MCP?</h3>
            <p>
              MCP is an open protocol that lets AI assistants connect to external tools and data sources.
              When you connect an AI tool to OpenSentry via MCP, it can list your cameras, check node
              status, get stream URLs, manage recording settings, and more — all through conversation.
            </p>

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
      "url": "https://opensentry-command.fly.dev/mcp",
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
      "url": "https://opensentry-command.fly.dev/mcp",
      "headers": {
        "Authorization": "Bearer osc_your_key_here"
      }
    }
  }
}`)}>Copy</button>
                  </div>
                  <p>Or via CLI:</p>
                  <div className="docs-code-block">
                    <code>claude mcp add --transport http opensentry https://opensentry-command.fly.dev/mcp --header "Authorization: Bearer osc_your_key"</code>
                    <button className="docs-copy-btn" onClick={() => copyToClipboard('claude mcp add --transport http opensentry https://opensentry-command.fly.dev/mcp --header "Authorization: Bearer osc_your_key"')}>Copy</button>
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
            <div className="docs-mcp-tools">
              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">list_cameras</span>
              </div>
              <p>List all cameras with status, codec, and group info.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_camera</span>
              </div>
              <p>Get details for a specific camera by ID.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_stream_url</span>
              </div>
              <p>Get a temporary pre-signed HLS stream URL for a camera.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">list_nodes</span>
              </div>
              <p>List all camera nodes with status and camera count.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_node</span>
              </div>
              <p>Get details for a specific node.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">list_camera_groups</span>
              </div>
              <p>List all camera groups in the organization.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method post">WRITE</span>
                <span className="docs-endpoint-path">create_camera_group</span>
              </div>
              <p>Create a new camera group with name, color, and icon.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method post">WRITE</span>
                <span className="docs-endpoint-path">assign_camera_to_group</span>
              </div>
              <p>Assign a camera to a group or remove it from its current group.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_recording_settings</span>
              </div>
              <p>View current recording config (continuous, scheduled, time range).</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method post">WRITE</span>
                <span className="docs-endpoint-path">update_recording_settings</span>
              </div>
              <p>Change recording settings: enable 24/7, scheduled recording, start/end times.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_stream_logs</span>
              </div>
              <p>View stream access history (who watched which camera, when).</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_stream_stats</span>
              </div>
              <p>Aggregated statistics: views by camera, user, and day.</p>

              <div className="docs-endpoint">
                <span className="docs-endpoint-method get">READ</span>
                <span className="docs-endpoint-path">get_system_status</span>
              </div>
              <p>High-level overview: total cameras, online/offline counts, node count, plan info.</p>
            </div>
          </section>

          {/* ── Plans & Limits ────────────────────────────────── */}
          <section className="docs-section" id="plans">
            <h2>Plans & Limits<a href="#plans" className="docs-anchor">#</a></h2>
            <p>OpenSentry offers three plans to fit different needs.</p>

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
            </ul>

            <p>Manage your subscription from <strong>Settings &gt; Subscription</strong> or the <Link to="/pricing">Pricing</Link> page.</p>
          </section>

          {/* ── Architecture ──────────────────────────────────── */}
          <section className="docs-section" id="architecture">
            <h2>Architecture<a href="#architecture" className="docs-anchor">#</a></h2>
            <p>OpenSentry uses a cloud-first architecture designed for simplicity and security.</p>

            <h3>Data Flow</h3>
            <div className="docs-flow-diagram">
              <div className="docs-flow-node">USB Camera</div>
              <span className="docs-flow-arrow">→</span>
              <div className="docs-flow-node">FFmpeg</div>
              <span className="docs-flow-arrow">→</span>
              <div className="docs-flow-node">CloudNode</div>
              <span className="docs-flow-arrow">→</span>
              <div className="docs-flow-node cloud">Tigris/S3</div>
              <span className="docs-flow-arrow">→</span>
              <div className="docs-flow-node">CDN</div>
              <span className="docs-flow-arrow">→</span>
              <div className="docs-flow-node">Browser</div>
            </div>

            <h3>How It Works</h3>
            <ol>
              <li><strong>CloudNode</strong> captures video from USB cameras using FFmpeg</li>
              <li>Video is encoded as HLS segments (2-second chunks) and uploaded to Tigris/S3 with BLAKE3 checksums</li>
              <li>The <strong>Command Center</strong> generates time-limited signed URLs for viewing</li>
              <li>Viewers watch via HLS from Fly.io's global CDN — no direct connection to your network</li>
            </ol>

            <h3>Security Model</h3>
            <ul>
              <li><strong>Outbound Only</strong> — CloudNode pushes to cloud. No inbound ports, no router config.</li>
              <li><strong>Signed URLs</strong> — Stream URLs are time-limited and signed. Can't be shared permanently.</li>
              <li><strong>API Key Auth</strong> — Node keys stored as SHA-256 hashes. Never stored in plaintext.</li>
              <li><strong>Clerk Organizations</strong> — Multi-tenant auth with admin and member roles.</li>
              <li><strong>HTTPS Everywhere</strong> — All traffic between CloudNode, Command Center, and viewers is encrypted.</li>
              <li><strong>MCP Keys</strong> — Separate API keys for MCP access, also SHA-256 hashed and org-scoped.</li>
            </ul>
          </section>

          {/* ── API Reference ─────────────────────────────────── */}
          <section className="docs-section" id="api-reference">
            <h2>API Reference<a href="#api-reference" className="docs-anchor">#</a></h2>
            <p>
              The Command Center exposes a REST API. Node endpoints use API key auth.
              User endpoints use Clerk JWT auth. MCP endpoints use MCP API key auth.
            </p>

            <h3>Node Endpoints</h3>
            <p>Used by CloudNode. Authenticate with <code>X-API-Key: {"your_api_key"}</code> header.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/nodes/register</span></div>
            <p>Register a node and its cameras. Returns camera ID mappings.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/nodes/heartbeat</span></div>
            <p>Send periodic heartbeat with camera status updates.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/upload-url</span></div>
            <p>Get a pre-signed URL for uploading an HLS segment to Tigris/S3.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/upload-complete</span></div>
            <p>Confirm segment upload. Triggers cleanup when retention threshold is reached.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/playlist</span></div>
            <p>Push the updated HLS playlist to cloud storage.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/codec</span></div>
            <p>Report detected video/audio codec information.</p>

            <h3>User Endpoints</h3>
            <p>Used by the web dashboard. Authenticate with Clerk JWT in <code>Authorization: Bearer</code> header.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/cameras</span></div>
            <p>List all cameras in the organization.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/stream.m3u8</span></div>
            <p>Get HLS playlist with pre-signed segment URLs for browser playback.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/nodes</span></div>
            <p>List all nodes in the organization. Admin only.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method post">POST</span><span className="docs-endpoint-path">/api/nodes</span></div>
            <p>Create a new node. Returns the API key (shown once).</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/settings</span></div>
            <p>Get all notification and recording settings.</p>

            <div className="docs-endpoint"><span className="docs-endpoint-method get">GET</span><span className="docs-endpoint-path">/api/audit/stream-logs</span></div>
            <p>Stream access history. Admin only. Filterable by camera and user.</p>

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
