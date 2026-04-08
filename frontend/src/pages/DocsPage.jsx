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
          <a href="#architecture" className="docs-sidebar-link">Architecture Overview</a>
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
            <p>Complete guides for deploying and using OpenSentry.</p>
          </div>

          <section className="docs-section" id="getting-started">
            <h2>
              Getting Started
              <a href="#getting-started" className="docs-anchor">#</a>
            </h2>
            <p>
              OpenSentry is a cloud-hosted security camera system with two main components:
            </p>
            <ul>
              <li><strong>Command Center</strong> - The web dashboard hosted on Fly.io</li>
              <li><strong>CloudNode</strong> - Local application that captures video and uploads to cloud</li>
            </ul>
            
            <h3>Prerequisites</h3>
            <ul>
              <li>A USB camera connected to your device</li>
              <li>An OpenSentry account (free)</li>
              <li>Windows, Linux, or macOS device</li>
            </ul>

            <h3>Quick Setup</h3>
            <div className="docs-steps">
              <div className="docs-step">
                <div className="docs-step-number">1</div>
                <div className="docs-step-content">
                  <h4>Create an account</h4>
                  <div className="docs-code-block">
                    <code>Visit opensentry-command.fly.dev and sign up</code>
                  </div>
                  <p>After signing up, create an organization. You'll be able to invite team members later.</p>
                </div>
              </div>
              
              <div className="docs-step">
                <div className="docs-step-number">2</div>
                <div className="docs-step-content">
                  <h4>Generate an API Key</h4>
                  <p>
                    Go to Settings in your dashboard and click "Add Node" to generate a new API key. 
                    Save this key - you'll need it for CloudNode setup.
                  </p>
                </div>
              </div>
              
              <div className="docs-step">
                <div className="docs-step-number">3</div>
                <div className="docs-step-content">
                  <h4>Install CloudNode</h4>
                  <div className="install-tabs">
                    <div className="install-tab-buttons">
                      <button
                        className={`install-tab-btn${os === 'linux' ? ' active' : ''}`}
                        onClick={() => setOs('linux')}
                      >
                        Linux
                      </button>
                      <button
                        className={`install-tab-btn${os === 'macos' ? ' active' : ''}`}
                        onClick={() => setOs('macos')}
                      >
                        macOS
                      </button>
                      <button
                        className={`install-tab-btn${os === 'windows' ? ' active' : ''}`}
                        onClick={() => setOs('windows')}
                      >
                        Windows
                      </button>
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
                  <p>
                    The installer will download CloudNode, check for ffmpeg, and guide you through setup.
                  </p>
                </div>
              </div>
              
              <div className="docs-step">
                <div className="docs-step-number">4</div>
                <div className="docs-step-content">
                  <h4>View your camera</h4>
                  <p>
                    Once CloudNode is running and connected, your camera will appear in the dashboard automatically.
                    Click on the camera to view the live HLS stream.
                  </p>
                </div>
              </div>
            </div>
          </section>

          <section className="docs-section" id="cloudnode-setup">
            <h2>
              CloudNode Setup
              <a href="#cloudnode-setup" className="docs-anchor">#</a>
            </h2>
            <p>
              CloudNode is a Rust application that runs on your premises. It captures video from USB cameras 
              and uploads HLS segments to Tigris cloud storage for global CDN delivery.
            </p>

            <h3>Installation</h3>
            <div className="install-tabs">
              <div className="install-tab-buttons">
                <button
                  className={`install-tab-btn${os === 'linux' ? ' active' : ''}`}
                  onClick={() => setOs('linux')}
                >
                  Linux
                </button>
                <button
                  className={`install-tab-btn${os === 'macos' ? ' active' : ''}`}
                  onClick={() => setOs('macos')}
                >
                  macOS
                </button>
                <button
                  className={`install-tab-btn${os === 'windows' ? ' active' : ''}`}
                  onClick={() => setOs('windows')}
                >
                  Windows
                </button>
              </div>
              <div className="install-tab-content">
                <div className="docs-code-block">
                  <code>{installCommands[os]}</code>
                  <button className="docs-copy-btn" onClick={() => copyToClipboard(installCommands[os])}>
                    {copied ? 'Copied!' : 'Copy'}
                  </button>
                </div>
                <p style={{ marginTop: '0.75rem', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                  {os === 'windows'
                    ? 'Run in PowerShell. The installer downloads CloudNode and checks for ffmpeg.'
                    : 'Run in your terminal. The installer downloads CloudNode and checks for ffmpeg.'}
                </p>
              </div>
            </div>

            <p>After installation, run the setup wizard to configure your API key:</p>
            <div className="docs-code-block">
              <code>{os === 'windows' ? 'opensentry-cloudnode.exe setup' : 'opensentry-cloudnode setup'}</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard(os === 'windows' ? 'opensentry-cloudnode.exe setup' : 'opensentry-cloudnode setup')}>
                Copy
              </button>
            </div>

            <h3>Configuration</h3>
            <p>
              CloudNode stores all configuration in a local SQLite database (<code>data/node.db</code>) created during setup.
              The API key is encrypted at rest. Key settings include:
            </p>
            <ul>
              <li><code>node_id</code> - Unique identifier for this node</li>
              <li><code>api_key</code> - Authentication key from Command Center (encrypted)</li>
              <li><code>api_url</code> - Command Center URL</li>
              <li><code>encoder</code> - Video encoder (auto-detected: NVENC, QSV, AMF, or libx264)</li>
            </ul>

            <h3>Running</h3>
            <p>After setup, run CloudNode:</p>
            <div className="docs-code-block">
              <code>./opensentry-cloudnode</code>
              <button className="docs-copy-btn" onClick={() => copyToClipboard('./opensentry-cloudnode')}>
                Copy
              </button>
            </div>
            <p>CloudNode will detect connected USB cameras and start streaming automatically.</p>
            
            <div className="docs-callout docs-callout-info">
              <p>
                <span className="docs-callout-icon">ℹ️</span>
                <span>CloudNode only makes outbound HTTPS requests - no inbound ports need to be opened on your firewall.</span>
              </p>
            </div>
          </section>

          <section className="docs-section" id="architecture">
            <h2>
              Architecture Overview
              <a href="#architecture" className="docs-anchor">#</a>
            </h2>
            <p>
              OpenSentry uses a cloud-first architecture designed for simplicity and security.
            </p>

            <h3>How It Works</h3>
            <ol>
              <li><strong>CloudNode</strong> captures video from your USB camera using FFmpeg</li>
              <li>Video is encoded as HLS segments (2-second chunks) and uploaded to Tigris/S3</li>
              <li>The <strong>Command Center</strong> provides signed URLs for viewing</li>
              <li>Viewers watch via HLS from the global Fly.io CDN - no direct connection to your network</li>
            </ol>

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

            <h3>Security Model</h3>
            <ul>
              <li><strong>Outbound Only:</strong> CloudNode only makes outbound HTTPS requests - no inbound ports required</li>
              <li><strong>Signed URLs:</strong> HLS URLs are time-limited and signed - viewers can't share permanent links</li>
              <li><strong>API Key Auth:</strong> Nodes authenticate with API keys, stored hashed in the database</li>
              <li><strong>Clerk Organizations:</strong> Multi-tenant auth with role-based permissions</li>
            </ul>
          </section>

          <section className="docs-section" id="api-reference">
            <h2>
              API Reference
              <a href="#api-reference" className="docs-anchor">#</a>
            </h2>
            <p>
              CloudNode communicates with Command Center via a REST API. All endpoints require authentication.
            </p>

            <h3>Authentication</h3>
            <p>All node API requests require the following header:</p>
            <div className="docs-code-block">
              <code>X-Node-API-Key: {"{your_api_key}"}</code>
            </div>

            <h3>Endpoints</h3>

            <h4>Node Registration</h4>
            <div className="docs-endpoint">
              <span className="docs-endpoint-method post">POST</span>
              <span className="docs-endpoint-path">/api/nodes/register</span>
            </div>
            <p>Register a new node and receive an API key.</p>

            <h4>Upload URL</h4>
            <div className="docs-endpoint">
              <span className="docs-endpoint-method post">POST</span>
              <span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/upload-url</span>
            </div>
            <p>Get a presigned URL for uploading an HLS segment directly to Tigris/S3.</p>

            <h4>Upload Complete</h4>
            <div className="docs-endpoint">
              <span className="docs-endpoint-method post">POST</span>
              <span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/upload-complete</span>
            </div>
            <p>Confirm a segment upload. Triggers automatic cleanup of old segments when retention threshold is reached.</p>

            <h4>Update Playlist</h4>
            <div className="docs-endpoint">
              <span className="docs-endpoint-method post">POST</span>
              <span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/playlist</span>
            </div>
            <p>Upload the current HLS playlist so Command Center can serve it to viewers.</p>

            <h4>Heartbeat</h4>
            <div className="docs-endpoint">
              <span className="docs-endpoint-method post">POST</span>
              <span className="docs-endpoint-path">/api/nodes/heartbeat</span>
            </div>
            <p>Send periodic heartbeat to indicate node is still active.</p>

            <h4>Stream Playlist</h4>
            <div className="docs-endpoint">
              <span className="docs-endpoint-method get">GET</span>
              <span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/stream.m3u8</span>
            </div>
            <p>Get the HLS playlist with presigned segment URLs for browser playback.</p>

            <h4>Report Codec</h4>
            <div className="docs-endpoint">
              <span className="docs-endpoint-method post">POST</span>
              <span className="docs-endpoint-path">/api/cameras/{"{camera_id}"}/codec</span>
            </div>
            <p>Report video and audio codec information for a camera stream.</p>

            <h3>Response Format</h3>
            <p>All responses are JSON with the format:</p>
            <div className="docs-code-block">
              <code>{"{"} "status": "success", "data": {"{...}"} {"}"}</code>
            </div>
          </section>

          <section className="docs-section">
            <h2>More Resources</h2>
            <div className="docs-resources">
              <a 
                href="https://github.com/SourceBox-LLC/OpenSentry-Command" 
                target="_blank" 
                rel="noopener noreferrer"
                className="docs-resource-card"
              >
                <div className="docs-resource-icon">💻</div>
                <h3>Command Center</h3>
                <p>Fork the repository on GitHub</p>
              </a>
              <a 
                href="https://github.com/SourceBox-LLC/opensentry-cloud-node" 
                target="_blank" 
                rel="noopener noreferrer"
                className="docs-resource-card"
              >
                <div className="docs-resource-icon">📹</div>
                <h3>CloudNode</h3>
                <p>Fork the repository on GitHub</p>
              </a>
              <a 
                href="https://github.com/SourceBox-LLC/OpenSentry-Command/issues" 
                target="_blank" 
                rel="noopener noreferrer"
                className="docs-resource-card"
              >
                <div className="docs-resource-icon">🐛</div>
                <h3>Report Issue</h3>
                <p>Found a bug? Let us know</p>
              </a>
            </div>
          </section>

          <div className="docs-cta">
            <p>Ready to set up your security camera system?</p>
            <Link to="/sign-up" className="docs-cta-btn">
              Create Free Account
            </Link>
          </div>
        </div>
      </main>
    </div>
  )
}

export default DocsPage