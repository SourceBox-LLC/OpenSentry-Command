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
        {os === 'windows'
          ? 'After the MSI finishes, open PowerShell as Administrator to run setup.'
          : 'Run in your terminal.'}
      </p>

      <h3>Setup Wizard</h3>
      <p>
        After installation, run the wizard to enrol the node and detect cameras:
      </p>
      <div className="docs-code-block">
        <code>{os === 'windows' ? 'sourcebox-sentry-cloudnode.exe setup' : 'sourcebox-sentry-cloudnode setup'}</code>
        <button className="docs-copy-btn" onClick={() => copyToClipboard(os === 'windows' ? 'sourcebox-sentry-cloudnode.exe setup' : 'sourcebox-sentry-cloudnode setup')}>Copy</button>
      </div>
      <p>The wizard walks through five steps:</p>
      <ol>
        <li>
          <strong>Prerequisites</strong> — detects platform, finds your USB cameras, verifies FFmpeg.
          On Windows, if FFmpeg isn't installed the wizard offers to{' '}
          <strong>download it for you</strong> (~150 MB, lands under{' '}
          <code>C:\ProgramData\SourceBoxSentry\ffmpeg\</code>). Linux/macOS users get pointed
          at <code>apt install ffmpeg</code> / <code>brew install ffmpeg</code>.
        </li>
        <li><strong>Configuration</strong> — prompts for your Node ID + API key (from Command Center → Settings → Add Node).</li>
        <li><strong>Install</strong> — saves the encrypted config and detects the best video encoder (NVENC / QSV / AMF, or libx264 fallback).</li>
        <li><strong>Verify</strong> — round-trips a credential check against Command Center.</li>
        <li><strong>Launch</strong> — optionally auto-starts the node.</li>
      </ol>
      <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
        On a fresh Windows machine with no FFmpeg, the whole flow takes about
        2 minutes including the FFmpeg download (depends on your connection).
      </p>

      {os === 'windows' && (
        <>
          <h3>Running as a Windows Service (MSI install)</h3>
          <p>
            If you installed via the MSI, CloudNode is registered as the{' '}
            <code>SourceBoxSentryCloudNode</code> service but is set to manual start so the first
            run can't fail before you've completed setup. After running setup, start it once
            and then flip it to auto-start so it survives reboots:
          </p>
          <div className="docs-code-block">
            <code>{`Start-Service SourceBoxSentryCloudNode
Set-Service -Name SourceBoxSentryCloudNode -StartupType Automatic`}</code>
            <button className="docs-copy-btn" onClick={() => copyToClipboard("Start-Service SourceBoxSentryCloudNode\nSet-Service -Name SourceBoxSentryCloudNode -StartupType Automatic")}>Copy</button>
          </div>
          <p>Standard service-management commands all work:</p>
          <ul>
            <li><code>Get-Service SourceBoxSentryCloudNode</code> — running / stopped status</li>
            <li><code>Stop-Service SourceBoxSentryCloudNode</code> / <code>Restart-Service SourceBoxSentryCloudNode</code></li>
            <li><code>Get-Content -Wait C:\ProgramData\SourceBoxSentry\logs\cloudnode-service.<i>YYYY-MM-DD</i></code> — tail today's service log</li>
          </ul>

          <h3>Uninstalling</h3>
          <p>
            Use <strong>Settings → Apps → Installed apps → SourceBox Sentry CloudNode → Uninstall</strong>.
            That stops the service, removes the binary, removes the Windows Service
            registration, and removes everything under{' '}
            <code>C:\ProgramData\SourceBoxSentry\</code> — including your encrypted config,
            recordings, and the auto-installed FFmpeg. After uninstall the machine is
            in a true "never installed" state.
          </p>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
            Upgrades (re-running a newer MSI) preserve everything under ProgramData;
            only an explicit uninstall wipes it. The CLI{' '}
            <code>sourcebox-sentry-cloudnode uninstall</code> subcommand is for source-built
            installs and redirects MSI users to Settings → Apps if you accidentally
            run it on an MSI machine.
          </p>

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
        <li><code>$SOURCEBOX_SENTRY_DATA_DIR/node.db</code> if the env var is set (Docker)</li>
        <li><code>./data/node.db</code> if it already exists (legacy / <code>cargo build</code> installs)</li>
        <li><code>C:\ProgramData\SourceBoxSentry\node.db</code> on Windows MSI installs</li>
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
        <code>{os === 'windows' ? '.\\sourcebox-sentry-cloudnode.exe' : './sourcebox-sentry-cloudnode'}</code>
        <button className="docs-copy-btn" onClick={() => copyToClipboard(os === 'windows' ? '.\\sourcebox-sentry-cloudnode.exe' : './sourcebox-sentry-cloudnode')}>Copy</button>
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
