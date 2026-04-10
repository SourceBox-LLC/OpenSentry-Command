import { useState, useRef, useEffect } from "react"

function AddNodeModal({ isOpen, onClose, onCreate }) {
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [credentials, setCredentials] = useState(null)
  const [os, setOs] = useState("linux")
  const inputRef = useRef(null)

  useEffect(() => {
    const ua = navigator.userAgent.toLowerCase()
    if (ua.includes('win')) setOs('windows')
    else if (ua.includes('mac')) setOs('macos')
    else setOs('linux')
  }, [])

  async function handleCreateClick() {
    const name = inputRef.current?.value

    if (!name || !name.trim()) {
      setError("Please enter a node name")
      return
    }

    setLoading(true)
    setError(null)

    try {
      const result = await onCreate(name.trim())
      setCredentials(result)
      setStep(2)
    } catch (err) {
      setError(err.message || "Failed to create node")
    } finally {
      setLoading(false)
    }
  }

  const base = window.location.origin
  const installCommands = {
    linux: `curl -fsSL ${base}/install.sh | bash`,
    macos: `curl -fsSL ${base}/install.sh | bash`,
    windows: `irm ${base}/install.ps1 | iex`,
  }

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text)
  }

  const handleClose = () => {
    setStep(1)
    setError(null)
    setCredentials(null)
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{step === 1 ? "Add Camera Node" : "Node Created"}</h2>
          <button className="modal-close" onClick={handleClose}>&times;</button>
        </div>

        {step === 1 && (
          <div className="modal-body">
            <p className="modal-description">
              Give your camera node a name to identify it (e.g., "Home", "Office", "Garage").
            </p>
            
            <div className="form-group">
              <label className="form-label" htmlFor="nodeName">Node Name</label>
              <input
                ref={inputRef}
                id="nodeName"
                name="nodeName"
                className="form-input"
                type="text"
                placeholder="e.g., Home"
                autoFocus
                disabled={loading}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault()
                    handleCreateClick()
                  }
                }}
              />
            </div>

            {error && (
              <div className="error-message">{error}</div>
            )}

            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleClose}
                disabled={loading}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleCreateClick}
                disabled={loading}
              >
                {loading ? "Creating..." : "Create Node"}
              </button>
            </div>
          </div>
        )}

        {step === 2 && credentials && (
          <div className="modal-body">
            <div className="warning-banner">
              <span className="warning-icon">⚠️</span>
              <div>
                <strong>Save These Credentials</strong>
                <p>You won't be able to see the API key again!</p>
              </div>
            </div>

            <div className="credentials-box">
              <div className="credential-item">
                <label>Node ID</label>
                <div className="credential-value">
                  <code>{credentials.node_id}</code>
                  <button
                    className="btn btn-small"
                    onClick={() => handleCopy(credentials.node_id)}
                  >
                    Copy
                  </button>
                </div>
              </div>

              <div className="credential-item">
                <label>API Key</label>
                <div className="credential-value">
                  <code>{credentials.api_key}</code>
                  <button
                    className="btn btn-small"
                    onClick={() => handleCopy(credentials.api_key)}
                  >
                    Copy
                  </button>
                </div>
              </div>
            </div>

            <div className="command-section">
              <h4>Deploy Your Node</h4>

              <div className="deployment-content">
                <div className="command-box">
                  <h5>1. Install CloudNode:</h5>
                  <div className="install-tabs">
                    <div className="install-tab-buttons">
                      <button className={`install-tab-btn${os === 'linux' ? ' active' : ''}`} onClick={() => setOs('linux')}>Linux</button>
                      <button className={`install-tab-btn${os === 'macos' ? ' active' : ''}`} onClick={() => setOs('macos')}>macOS</button>
                      <button className={`install-tab-btn${os === 'windows' ? ' active' : ''}`} onClick={() => setOs('windows')}>Windows</button>
                    </div>
                  </div>
                  <code>{installCommands[os]}</code>
                  <button className="btn btn-small" onClick={() => handleCopy(installCommands[os])}>Copy</button>
                </div>
                <div className="command-box">
                  <h5>2. Run the setup wizard:</h5>
                  <code>{os === 'windows' ? 'opensentry-cloudnode.exe setup' : 'opensentry-cloudnode setup'}</code>
                  <button className="btn btn-small" onClick={() => handleCopy(os === 'windows' ? 'opensentry-cloudnode.exe setup' : 'opensentry-cloudnode setup')}>Copy</button>
                </div>
                <div className="command-note">
                  <strong>Tip:</strong> The setup wizard will ask for your Node ID and API Key shown above.
                </div>
                <div className="command-box">
                  <h5>3. Start CloudNode:</h5>
                  <code>{os === 'windows' ? 'opensentry-cloudnode.exe' : './opensentry-cloudnode'}</code>
                  <button className="btn btn-small" onClick={() => handleCopy(os === 'windows' ? 'opensentry-cloudnode.exe' : './opensentry-cloudnode')}>Copy</button>
                </div>
              </div>
            </div>

            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleClose}
              >
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default AddNodeModal