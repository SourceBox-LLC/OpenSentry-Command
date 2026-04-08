import { useState, useEffect } from "react"
import { useAuth, useOrganization } from "@clerk/clerk-react"
import { getNodes, createNode as createNodeApi, rotateNodeKey, deleteNode as deleteNodeApi, wipeStreamLogs, fullReset } from "../services/api"
import AddNodeModal from "../components/AddNodeModal.jsx"
import KeyRotationModal from "../components/KeyRotationModal.jsx"

function formatRelativeTime(dateString) {
  if (!dateString) return ""
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return "Just now"
  if (diffMins < 60) return `${diffMins} min${diffMins === 1 ? "" : "s"} ago`
  if (diffHours < 24) return `${diffHours} hr${diffHours === 1 ? "" : "s"} ago`
  if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`
  return date.toLocaleDateString()
}

function SettingsPage() {
  const { getToken } = useAuth()
  const { organization } = useOrganization()
  const [nodes, setNodes] = useState([])
  const [nodesLoading, setNodesLoading] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)
  const [showRotateModal, setShowRotateModal] = useState(false)
  const [selectedNode, setSelectedNode] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(null)
  const [deleting, setDeleting] = useState(false)

  // Danger Zone
  const [dangerAction, setDangerAction] = useState(null)
  const [dangerConfirmText, setDangerConfirmText] = useState("")
  const [dangerLoading, setDangerLoading] = useState(false)
  const [dangerResult, setDangerResult] = useState(null)

  useEffect(() => {
    if (organization) {
      loadNodes()
    }
  }, [organization])

  const loadNodes = async () => {
    if (!organization) return

    try {
      setNodesLoading(true)
      const token = await getToken()
      const data = await getNodes(() => Promise.resolve(token))
      setNodes(data)
    } catch (err) {
      console.error("Failed to load nodes:", err)
    } finally {
      setNodesLoading(false)
    }
  }

  const handleCreateNode = async (name) => {
    const token = await getToken()

    try {
      const result = await createNodeApi(() => Promise.resolve(token), name)
      await loadNodes()
      return result
    } catch (err) {
      console.error("[SettingsPage] Failed to create node:", err)
      throw err
    }
  }

  const handleDeleteNode = async (nodeId) => {
    setDeleting(true)
    try {
      const token = await getToken()
      await deleteNodeApi(() => Promise.resolve(token), nodeId)
      await loadNodes()
      setDeleteConfirm(null)
    } catch (err) {
      console.error("[SettingsPage] Failed to delete node:", err)
    } finally {
      setDeleting(false)
    }
  }

  const handleRotateKey = async (nodeId) => {
    const token = await getToken()
    const result = await rotateNodeKey(() => Promise.resolve(token), nodeId)
    await loadNodes()
    return result
  }

  const openRotateModal = (node) => {
    setSelectedNode(node)
    setShowRotateModal(true)
  }

  const dangerActions = {
    "wipe-logs": {
      title: "Wipe All Stream Logs",
      description: "This will permanently delete all stream access logs and statistics for your organization. This cannot be undone.",
      confirmPhrase: "wipe logs",
      handler: async () => {
        const token = await getToken()
        return await wipeStreamLogs(() => Promise.resolve(token))
      },
    },
    "full-reset": {
      title: "Full Organization Reset",
      description: "This will delete ALL nodes (notifying them to wipe local data), remove all cloud storage, clear all logs, and reset all settings. Your organization will be returned to a completely fresh state. This cannot be undone.",
      confirmPhrase: "reset everything",
      handler: async () => {
        const token = await getToken()
        const result = await fullReset(() => Promise.resolve(token))
        await loadNodes()
        return result
      },
    },
  }

  const handleDangerAction = async () => {
    const action = dangerActions[dangerAction]
    if (!action || dangerConfirmText !== action.confirmPhrase) return

    setDangerLoading(true)
    try {
      const result = await action.handler()
      setDangerResult(result)
    } catch (err) {
      console.error("Danger action failed:", err)
      setDangerResult({ error: err.message })
    } finally {
      setDangerLoading(false)
    }
  }

  const closeDangerModal = () => {
    setDangerAction(null)
    setDangerConfirmText("")
    setDangerResult(null)
    setDangerLoading(false)
  }

  if (!organization) {
    return (
      <div className="settings-container">
        <h1 className="page-title">Settings</h1>
        <p className="text-muted">Please select an organization to view settings.</p>
      </div>
    )
  }

  return (
    <div className="settings-container">
      <h1 className="page-title">Settings</h1>

      <div className="settings-section">
        <h2>Camera Nodes</h2>
        <p className="section-description">
          Manage your camera nodes. Each node can connect multiple cameras to your Command Center.
        </p>

        <div className="nodes-list">
          {nodesLoading ? (
            <div className="loading-spinner"></div>
          ) : nodes.length === 0 ? (
            <div className="empty-nodes">
              <p>No camera nodes configured yet.</p>
              <button
                className="btn btn-primary"
                onClick={() => setShowAddModal(true)}
              >
                Add Your First Node
              </button>
            </div>
          ) : (
            <>
              {nodes.map((node) => (
                <div key={node.node_id} className="node-item">
                  <div className="node-info">
                    <div className="node-header-row">
                      <span className="node-name">{node.name || `Node ${node.node_id}`}</span>
                      <span className={`node-status status-${node.status}`}>
                        <span className="status-dot"></span>
                        {node.status}
                      </span>
                    </div>
                    <div className="node-meta">
                      <span className="node-id">ID: {node.node_id}</span>
                      {node.camera_count > 0 && (
                        <span className="node-cameras">{node.camera_count} camera{node.camera_count === 1 ? "" : "s"}</span>
                      )}
                      {node.last_seen && (
                        <span className="node-last-seen">
                          {formatRelativeTime(node.last_seen)}
                        </span>
                      )}
                    </div>
                    {node.key_rotated_at && (
                      <span className="node-key-rotated">
                        Key rotated {formatRelativeTime(node.key_rotated_at)}
                      </span>
                    )}
                  </div>
                  <div className="node-actions">
                    <button
                      className="btn btn-small btn-secondary"
                      onClick={() => openRotateModal(node)}
                    >
                      Rotate Key
                    </button>
                    <button
                      className="btn btn-small btn-danger"
                      onClick={() => setDeleteConfirm(node.node_id)}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
              <button
                className="btn btn-primary add-node-btn"
                onClick={() => setShowAddModal(true)}
              >
                Add Node
              </button>
            </>
          )}
        </div>

        {deleteConfirm && (
          <div className="modal-overlay" onClick={() => !deleting && setDeleteConfirm(null)}>
            <div className="modal-content small" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h2>{deleting ? "Deleting Node..." : "Delete Node?"}</h2>
              </div>
              <div className="modal-body">
                {deleting ? (
                  <div className="delete-progress">
                    <div className="loading-spinner" />
                    <p>Removing node and associated cameras...</p>
                  </div>
                ) : (
                  <p>Are you sure you want to delete this node? This will also remove all associated cameras and their stored footage.</p>
                )}
                <div className="modal-actions">
                  <button
                    className="btn btn-secondary"
                    onClick={() => setDeleteConfirm(null)}
                    disabled={deleting}
                  >
                    Cancel
                  </button>
                  <button
                    className="btn btn-danger"
                    onClick={() => handleDeleteNode(deleteConfirm)}
                    disabled={deleting}
                  >
                    {deleting ? "Deleting..." : "Delete"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="settings-section">
        <h2>Organization</h2>
        <div className="org-info">
          <p><strong>Name:</strong> {organization?.name || "Unknown"}</p>
          <p><strong>ID:</strong> {organization?.id || "Unknown"}</p>
        </div>
      </div>

      <div className="settings-section danger-zone">
        <h2>Danger Zone</h2>
        <p className="section-description">
          Irreversible actions that affect your entire organization.
        </p>

        <div className="danger-actions">
          <div className="danger-item">
            <div className="danger-info">
              <h3>Wipe All Stream Logs</h3>
              <p>Delete all stream access logs and usage statistics.</p>
            </div>
            <button
              className="btn btn-danger"
              onClick={() => setDangerAction("wipe-logs")}
            >
              Wipe Logs
            </button>
          </div>

          <div className="danger-item">
            <div className="danger-info">
              <h3>Full Organization Reset</h3>
              <p>Delete all nodes, cameras, cloud storage, logs, and settings. Nodes will be notified to wipe local data.</p>
            </div>
            <button
              className="btn btn-danger"
              onClick={() => setDangerAction("full-reset")}
            >
              Reset Everything
            </button>
          </div>
        </div>

        {dangerAction && (
          <div className="modal-overlay" onClick={() => !dangerLoading && closeDangerModal()}>
            <div className="modal-content small" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h2>{dangerActions[dangerAction].title}</h2>
              </div>
              <div className="modal-body">
                {dangerResult ? (
                  <div className="danger-result">
                    {dangerResult.error ? (
                      <p className="danger-error">Failed: {dangerResult.error}</p>
                    ) : (
                      <>
                        <p className="danger-success">Operation completed successfully.</p>
                        {dangerResult.nodes_deleted !== undefined && (
                          <ul className="danger-summary">
                            <li>{dangerResult.nodes_deleted} node(s) deleted ({dangerResult.nodes_wiped} notified)</li>
                            <li>{dangerResult.cameras_deleted} camera(s) removed</li>
                            <li>{dangerResult.storage_cleaned} storage object(s) cleaned</li>
                            <li>{dangerResult.logs_deleted} log(s) deleted</li>
                            <li>{dangerResult.settings_deleted} setting(s) reset</li>
                          </ul>
                        )}
                        {dangerResult.deleted_logs !== undefined && (
                          <p>{dangerResult.deleted_logs} log(s) deleted.</p>
                        )}
                      </>
                    )}
                    <div className="modal-actions">
                      <button className="btn btn-secondary" onClick={closeDangerModal}>
                        Close
                      </button>
                    </div>
                  </div>
                ) : dangerLoading ? (
                  <div className="delete-progress">
                    <div className="loading-spinner" />
                    <p>Processing... This may take a moment.</p>
                  </div>
                ) : (
                  <>
                    <p className="danger-warning">{dangerActions[dangerAction].description}</p>
                    <div className="danger-confirm-input">
                      <label>
                        Type <strong>{dangerActions[dangerAction].confirmPhrase}</strong> to confirm:
                      </label>
                      <input
                        type="text"
                        value={dangerConfirmText}
                        onChange={(e) => setDangerConfirmText(e.target.value)}
                        placeholder={dangerActions[dangerAction].confirmPhrase}
                        autoFocus
                      />
                    </div>
                    <div className="modal-actions">
                      <button className="btn btn-secondary" onClick={closeDangerModal}>
                        Cancel
                      </button>
                      <button
                        className="btn btn-danger"
                        onClick={handleDangerAction}
                        disabled={dangerConfirmText !== dangerActions[dangerAction].confirmPhrase}
                      >
                        {dangerActions[dangerAction].title}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      <AddNodeModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onCreate={handleCreateNode}
      />

      <KeyRotationModal
        isOpen={showRotateModal}
        onClose={() => {
          setShowRotateModal(false)
          setSelectedNode(null)
        }}
        node={selectedNode}
        onRotate={handleRotateKey}
      />
    </div>
  )
}

export default SettingsPage
