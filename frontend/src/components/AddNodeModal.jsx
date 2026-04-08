import { useState, useRef } from "react"

const NODE_API_URL = import.meta.env.VITE_API_URL || window.location.origin

function AddNodeModal({ isOpen, onClose, onCreate }) {
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [credentials, setCredentials] = useState(null)
  const [deploymentMode, setDeploymentMode] = useState("docker")
  const inputRef = useRef(null)

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

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text)
  }

  const handleCopyDockerCommand = () => {
    const cmd = `docker exec opensentry-cloudnode opensentry-cloudnode \\
  --node-id ${credentials.node_id} \\
  --api-key ${credentials.api_key} \\
  --api-url ${NODE_API_URL}`
    navigator.clipboard.writeText(cmd)
  }

  const handleCopyNativeCommand = () => {
    const cmd = `cargo run -- \\
  --node-id ${credentials.node_id} \\
  --api-key ${credentials.api_key} \\
  --api-url ${NODE_API_URL}`
    navigator.clipboard.writeText(cmd)
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
              
              <div className="deployment-tabs">
                <button 
                  className={`deployment-tab ${deploymentMode === "docker" ? "active" : ""}`}
                  onClick={() => setDeploymentMode("docker")}
                >
                  Docker (Recommended)
                </button>
                <button 
                  className={`deployment-tab ${deploymentMode === "native" ? "active" : ""}`}
                  onClick={() => setDeploymentMode("native")}
                >
                  Native Binary
                </button>
              </div>

              {deploymentMode === "docker" && (
                <div className="deployment-content">
                  <p className="deployment-description">
                    Containerized deployment with FFmpeg included. Best for production use.
                  </p>
                  <div className="command-box">
                    <h5>1. Create .env file:</h5>
                    <code style={{ whiteSpace: "pre-wrap" }}>{`OPENSENTRY_NODE_ID=${credentials.node_id}
OPENSENTRY_API_KEY=${credentials.api_key}
OPENSENTRY_API_URL=${NODE_API_URL}`}</code>
                    <button
                      className="btn btn-small"
                      onClick={() => handleCopy(`OPENSENTRY_NODE_ID=${credentials.node_id}\nOPENSENTRY_API_KEY=${credentials.api_key}\nOPENSENTRY_API_URL=${NODE_API_URL}`)}
                    >
                      Copy
                    </button>
                  </div>
                  <div className="command-box">
                    <h5>2. Pull and run:</h5>
                    <code style={{ whiteSpace: "pre-wrap" }}>{`docker pull opensentry-cloudnode:latest
docker run -d \\
  --name opensentry-cloudnode \\
  --device /dev/video0 \\
  --env-file .env \\
  -p 8080:8080 \\
  opensentry-cloudnode:latest`}</code>
                    <button
                      className="btn btn-small"
                      onClick={() => handleCopy(`docker pull opensentry-cloudnode:latest\ndocker run -d \\\n  --name opensentry-cloudnode \\\n  --device /dev/video0 \\\n  --env-file .env \\\n  -p 8080:8080 \\\n  opensentry-cloudnode:latest`)}
                    >
                      Copy
                    </button>
                  </div>
                </div>
              )}

              {deploymentMode === "native" && (
                <div className="deployment-content">
                  <p className="deployment-description">
                    Run directly with Cargo. Requires FFmpeg installed separately. Good for development.
                  </p>
                  <div className="command-box">
                    <code style={{ whiteSpace: "pre-wrap" }}>{`cargo run -- \\
  --node-id ${credentials.node_id} \\
  --api-key ${credentials.api_key} \\
  --api-url ${NODE_API_URL}`}</code>
                    <button
                      className="btn btn-small copy-command-btn"
                      onClick={handleCopyNativeCommand}
                    >
                      Copy Command
                    </button>
                  </div>
                  <div className="command-note">
                    <strong>Note:</strong> Requires Rust and FFmpeg to be installed.
                  </div>
                </div>
              )}
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