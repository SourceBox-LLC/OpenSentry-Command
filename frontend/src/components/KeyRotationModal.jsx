import { useState } from "react"

const NODE_API_URL = import.meta.env.VITE_API_URL || window.location.origin

function KeyRotationModal({ isOpen, onClose, node, onRotate }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [credentials, setCredentials] = useState(null)

  const handleRotate = async () => {
    if (!node) return

    setLoading(true)
    setError(null)

    try {
      const result = await onRotate(node.node_id)
      setCredentials(result)
    } catch (err) {
      setError(err.message || "Failed to rotate key")
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text)
  }

  const handleCopyCommand = () => {
    if (!credentials) return
    const cmd = `cargo run -- --node-id ${credentials.node_id} --api-key ${credentials.api_key} --api-url ${NODE_API_URL}`
    navigator.clipboard.writeText(cmd)
  }

  const handleClose = () => {
    setCredentials(null)
    setError(null)
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{credentials ? "API Key Rotated" : "Rotate API Key"}</h2>
          <button className="modal-close" onClick={handleClose}>&times;</button>
        </div>

        {!credentials ? (
          <div className="modal-body">
            <p className="modal-description">
              Rotating the API key will immediately invalidate the old key.
              You'll need to update your CloudNode configuration with the new key.
            </p>
            
            <div className="node-info-box">
              <div className="info-row">
                <span className="info-label">Node:</span>
                <span className="info-value">{node?.name || `Node ${node?.node_id}`}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Node ID:</span>
                <span className="info-value">{node?.node_id}</span>
              </div>
              {node?.key_rotated_at && (
                <div className="info-row">
                  <span className="info-label">Last rotated:</span>
                  <span className="info-value">{new Date(node.key_rotated_at).toLocaleString()}</span>
                </div>
              )}
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
                className="btn btn-danger"
                onClick={handleRotate}
                disabled={loading}
              >
                {loading ? "Rotating..." : "Rotate Key"}
              </button>
            </div>
          </div>
        ) : (
          <div className="modal-body">
            <div className="warning-banner">
              <span className="warning-icon">⚠️</span>
              <div>
                <strong>Old key invalidated!</strong>
                <p>Update your CloudNode configuration immediately.</p>
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
                <label>New API Key</label>
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
              <h4>Run this command on your device:</h4>
              <div className="command-box">
                <code>
                  cargo run -- \<br/>
                  &nbsp;&nbsp;--node-id {credentials.node_id} \<br/>
                  &nbsp;&nbsp;--api-key {credentials.api_key} \<br/>
                  &nbsp;&nbsp;--api-url {NODE_API_URL}
                </code>
                <button
                  className="btn btn-small copy-command-btn"
                  onClick={handleCopyCommand}
                >
                  Copy Command
                </button>
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

export default KeyRotationModal