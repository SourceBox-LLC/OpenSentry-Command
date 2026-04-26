import { OsTabs, useDocs } from "./context"


function CloudNodeSetup() {
  const { os, copyToClipboard } = useDocs()

  return (
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
  )
}

export default CloudNodeSetup
