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

      {os === 'windows' && (
        <div className="docs-callout docs-callout-info" style={{ marginTop: '1rem' }}>
          <p>
            <span className="docs-callout-icon">🪟</span>
            <span>
              <strong>Recommended for always-on cameras:</strong> use the{' '}
              <a
                href="https://github.com/SourceBox-LLC/opensentry-cloud-node/releases/latest/download/opensentry-cloudnode-windows-x86_64.msi"
                target="_blank"
                rel="noopener noreferrer"
              >
                MSI installer
              </a>
              . It registers CloudNode as a Windows Service that survives logout and reboots,
              installs to <code>C:\Program Files\OpenSentry CloudNode\</code>, and stores config under{' '}
              <code>C:\ProgramData\OpenSentry\</code>. The MSI is currently <strong>unsigned</strong> —
              SmartScreen will warn "Windows protected your PC" on first run. Click{' '}
              <strong>More info → Run anyway</strong>. Code signing is on the roadmap.
            </span>
          </p>
        </div>
      )}

      <h3>Setup Wizard</h3>
      <p>After installation, configure your API key:</p>
      <div className="docs-code-block">
        <code>{os === 'windows' ? 'opensentry-cloudnode.exe setup' : 'opensentry-cloudnode setup'}</code>
        <button className="docs-copy-btn" onClick={() => copyToClipboard(os === 'windows' ? 'opensentry-cloudnode.exe setup' : 'opensentry-cloudnode setup')}>Copy</button>
      </div>

      {os === 'windows' && (
        <>
          <h3>Running as a Windows Service (MSI install)</h3>
          <p>
            If you installed via the MSI, CloudNode is registered as the{' '}
            <code>OpenSentryCloudNode</code> service but is set to manual start so the first
            run can't fail before you've completed setup. After running setup, start it once
            and then flip it to auto-start so it survives reboots:
          </p>
          <div className="docs-code-block">
            <code>{`Start-Service OpenSentryCloudNode
Set-Service -Name OpenSentryCloudNode -StartupType Automatic`}</code>
            <button className="docs-copy-btn" onClick={() => copyToClipboard("Start-Service OpenSentryCloudNode\nSet-Service -Name OpenSentryCloudNode -StartupType Automatic")}>Copy</button>
          </div>
          <p>Standard service-management commands all work:</p>
          <ul>
            <li><code>Get-Service OpenSentryCloudNode</code> — running / stopped status</li>
            <li><code>Stop-Service OpenSentryCloudNode</code> / <code>Restart-Service OpenSentryCloudNode</code></li>
            <li><code>Get-Content -Wait C:\ProgramData\OpenSentry\logs\cloudnode-service.<i>YYYY-MM-DD</i></code> — tail today's service log</li>
          </ul>
          <p>
            See the CloudNode <a href="https://github.com/SourceBox-LLC/opensentry-cloud-node#running-as-a-windows-service" target="_blank" rel="noopener noreferrer">README</a> for the full reference.
          </p>
        </>
      )}

      <h3>Configuration</h3>
      <p>
        CloudNode stores all configuration in a local SQLite database. Resolution order:
      </p>
      <ul>
        <li><code>$OPENSENTRY_DATA_DIR/node.db</code> if the env var is set (Docker)</li>
        <li><code>./data/node.db</code> if it already exists (legacy / <code>cargo build</code> installs)</li>
        <li><code>C:\ProgramData\OpenSentry\node.db</code> on Windows MSI installs</li>
        <li><code>./data/node.db</code> otherwise (fresh manual install on Linux/macOS)</li>
      </ul>
      <p>The API key is encrypted at rest. Key settings:</p>
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
