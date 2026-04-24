import { useState, useEffect, useRef } from "react"
import { Link } from "react-router-dom"
import { useAuth, useOrganization } from "@clerk/clerk-react"
import { getNodes, createNode as createNodeApi, rotateNodeKey, deleteNode as deleteNodeApi, wipeStreamLogs, fullReset, getSettings, updateRecordingSettings, updateNotificationSettings } from "../services/api"
import { useToasts } from "../hooks/useToasts.jsx"
import { usePlanInfo } from "../hooks/usePlanInfo.jsx"
import AddNodeModal from "../components/AddNodeModal.jsx"
import KeyRotationModal from "../components/KeyRotationModal.jsx"
import UpgradeModal from "../components/UpgradeModal.jsx"
import WebhookSettings from "../components/WebhookSettings.jsx"

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
  const { organization, membership } = useOrganization()
  const { showToast } = useToasts()
  const { planInfo, refreshPlanInfo } = usePlanInfo()
  const [nodes, setNodes] = useState([])
  const [nodesLoading, setNodesLoading] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)
  const [showRotateModal, setShowRotateModal] = useState(false)
  const [selectedNode, setSelectedNode] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(null)
  const [deleting, setDeleting] = useState(false)

  // Recording settings
  const [recording, setRecording] = useState(null)
  const [settingsLoading, setSettingsLoading] = useState(false)
  const [settingsSaving, setSettingsSaving] = useState(false)

  // Notification preferences (same /api/settings payload, separate subsection).
  const [notifications, setNotifications] = useState(null)
  const [notificationsSaving, setNotificationsSaving] = useState(false)

  // Upgrade modal
  const [upgradeFeature, setUpgradeFeature] = useState(null)

  // Node status tracking
  const prevNodesRef = useRef(null)

  // Danger Zone
  const [dangerAction, setDangerAction] = useState(null)
  const [dangerConfirmText, setDangerConfirmText] = useState("")
  const [dangerLoading, setDangerLoading] = useState(false)
  const [dangerResult, setDangerResult] = useState(null)

  useEffect(() => {
    if (organization) {
      loadNodes()
      loadSettings()
      // Poll nodes every 30s to detect status changes
      const interval = setInterval(loadNodes, 30000)
      return () => clearInterval(interval)
    }
  }, [organization])

  const loadSettings = async () => {
    try {
      setSettingsLoading(true)
      const token = await getToken()
      const data = await getSettings(() => Promise.resolve(token))
      setRecording(data.recording)
      // Backend defaults to "all on" when the notifications block is
      // missing, but be defensive for older backends that don't send it.
      setNotifications(
        data.notifications || {
          motion_notifications: true,
          camera_transition_notifications: true,
          node_transition_notifications: true,
        },
      )
    } catch (err) {
      console.error("Failed to load settings:", err)
      showToast("Failed to load settings", "error")
    } finally {
      setSettingsLoading(false)
    }
  }

  const saveRecording = async (updated) => {
    setSettingsSaving(true)
    try {
      const token = await getToken()
      await updateRecordingSettings(() => Promise.resolve(token), updated)
      setRecording(updated)
      showToast("Recording settings saved", "success")
    } catch (err) {
      showToast(err.message || "Failed to save recording settings", "error")
    } finally {
      setSettingsSaving(false)
    }
  }

  const handleRecordingToggle = (key) => {
    const updated = { ...recording, [key]: !recording[key] }
    saveRecording(updated)
  }

  const handleRecordingChange = (key, value) => {
    const updated = { ...recording, [key]: value }
    saveRecording(updated)
  }

  const saveNotifications = async (updated) => {
    // Optimistic update — keep the toggle responsive even if the save
    // is slow.  Rollback to server state if the request fails.
    const previous = notifications
    setNotifications(updated)
    setNotificationsSaving(true)
    try {
      const token = await getToken()
      await updateNotificationSettings(() => Promise.resolve(token), updated)
      showToast("Notification settings saved", "success")
    } catch (err) {
      setNotifications(previous)
      showToast(err.message || "Failed to save notification settings", "error")
    } finally {
      setNotificationsSaving(false)
    }
  }

  const handleNotificationToggle = (key) => {
    if (!notifications) return
    saveNotifications({ ...notifications, [key]: !notifications[key] })
  }

  const loadNodes = async () => {
    if (!organization) return

    try {
      setNodesLoading(true)
      const token = await getToken()
      const data = await getNodes(() => Promise.resolve(token))

      // Detect nodes that just went offline or came back online
      if (prevNodesRef.current) {
        const prevMap = Object.fromEntries(prevNodesRef.current.map(n => [n.node_id, n]))
        for (const node of data) {
          const prev = prevMap[node.node_id]
          if (prev && prev.status !== "offline" && node.status === "offline") {
            showToast(`Node "${node.name}" went offline`, "warning")
          } else if (prev && prev.status === "offline" && node.status !== "offline") {
            showToast(`Node "${node.name}" is back online`, "success")
          }
        }
      }
      prevNodesRef.current = data

      setNodes(data)
    } catch (err) {
      console.error("Failed to load nodes:", err)
      // Only toast on first load error, not poll errors
      if (!prevNodesRef.current) showToast("Failed to load camera nodes", "error")
    } finally {
      setNodesLoading(false)
    }
  }

  const handleCreateNode = async (name) => {
    const token = await getToken()

    try {
      const result = await createNodeApi(() => Promise.resolve(token), name)
      await loadNodes()
      await refreshPlanInfo()
      showToast(`Node "${name}" created successfully`, "success")
      // Stash a marker so the dashboard's HeartbeatBanner can pick it up
      // and celebrate the first heartbeat. Scoped by org to avoid leaking
      // across workspace switches.
      try {
        if (result?.node_id && organization?.id) {
          localStorage.setItem(
            `os.recentlyCreatedNode.${organization.id}`,
            JSON.stringify({
              node_id: result.node_id,
              name,
              created_at: Date.now(),
            })
          )
        }
      } catch (_) { /* localStorage unavailable — banner just won't show */ }
      return result
    } catch (err) {
      console.error("[SettingsPage] Failed to create node:", err)
      showToast(err.message || "Failed to create node", "error")
      throw err
    }
  }

  const handleDeleteNode = async (nodeId) => {
    setDeleting(true)
    try {
      const token = await getToken()
      await deleteNodeApi(() => Promise.resolve(token), nodeId)
      await loadNodes()
      await refreshPlanInfo()
      setDeleteConfirm(null)
      showToast("Node deleted and storage cleaned up", "success")
    } catch (err) {
      console.error("[SettingsPage] Failed to delete node:", err)
      showToast(err.message || "Failed to delete node", "error")
    } finally {
      setDeleting(false)
    }
  }

  const handleRotateKey = async (nodeId) => {
    const token = await getToken()
    try {
      const result = await rotateNodeKey(() => Promise.resolve(token), nodeId)
      await loadNodes()
      showToast("API key rotated — update your CloudNode config", "warning")
      return result
    } catch (err) {
      showToast(err.message || "Failed to rotate API key", "error")
      throw err
    }
  }

  const handleAddNodeClick = () => {
    if (planInfo && planInfo.usage.nodes >= planInfo.limits.max_nodes) {
      setUpgradeFeature("nodes")
    } else {
      setShowAddModal(true)
    }
  }

  const openRotateModal = (node) => {
    setSelectedNode(node)
    setShowRotateModal(true)
  }

  const dangerActions = {
    "wipe-logs": {
      title: "Wipe All Logs",
      description: "This will permanently delete all stream access logs, MCP activity logs, and statistics for your organization. This cannot be undone.",
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
      showToast(`${action.title} completed`, "success")
    } catch (err) {
      console.error("Danger action failed:", err)
      setDangerResult({ error: err.message })
      showToast(`${action.title} failed`, "error")
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
                onClick={handleAddNodeClick}
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
                      {node.node_version && (
                        <span
                          className="node-version"
                          title={`CloudNode v${node.node_version}`}
                        >
                          v{node.node_version}
                        </span>
                      )}
                      {node.last_seen && (
                        <span className="node-last-seen">
                          {formatRelativeTime(node.last_seen)}
                        </span>
                      )}
                    </div>
                    {node.update_available && (
                      <div className="node-update-available" role="status">
                        <span className="node-update-icon" aria-hidden="true">⬆</span>
                        <div className="node-update-body">
                          <strong>Update available: v{node.update_available}</strong>
                          {node.node_version && (
                            <span className="node-update-current">
                              {" "}(currently v{node.node_version})
                            </span>
                          )}
                          <p className="node-update-hint">
                            Re-run the installer on this node to upgrade.
                          </p>
                        </div>
                      </div>
                    )}
                    {node.key_rotated_at && (
                      <span className="node-key-rotated">
                        Key rotated {formatRelativeTime(node.key_rotated_at)}
                      </span>
                    )}
                    {node.last_register_error && (
                      <div className="node-register-error" role="alert">
                        <span className="node-register-error-icon">⚠️</span>
                        <div className="node-register-error-body">
                          <strong>Registration failing</strong>
                          <p>{node.last_register_error}</p>
                          {node.last_register_error_at && (
                            <span className="node-register-error-time">
                              {formatRelativeTime(node.last_register_error_at)}
                            </span>
                          )}
                          <button
                            type="button"
                            className="btn btn-small btn-primary"
                            onClick={() => openRotateModal(node)}
                          >
                            Rotate Key
                          </button>
                        </div>
                      </div>
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
                onClick={handleAddNodeClick}
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
        <div className="org-card">
          <div className="org-card-header">
            {organization?.imageUrl ? (
              <img src={organization.imageUrl} alt="" className="org-avatar" />
            ) : (
              <div className="org-avatar org-avatar-fallback">
                {(organization?.name || "O").charAt(0).toUpperCase()}
              </div>
            )}
            <div className="org-card-title">
              <h3>{organization?.name || "Unknown"}</h3>
              <span className="org-role-badge">
                {membership?.role === "org:admin" ? "Admin" : "Member"}
              </span>
            </div>
          </div>
          <div className="org-card-details">
            <div className="org-detail">
              <span className="org-detail-label">Members</span>
              <span className="org-detail-value">{organization?.membersCount || 1}</span>
            </div>
            <div className="org-detail">
              <span className="org-detail-label">Created</span>
              <span className="org-detail-value">
                {organization?.createdAt
                  ? new Date(organization.createdAt).toLocaleDateString()
                  : "—"}
              </span>
            </div>
            <div className="org-detail">
              <span className="org-detail-label">Nodes</span>
              <span className="org-detail-value">{nodes.length}</span>
            </div>
            <div className="org-detail">
              <span className="org-detail-label">Cameras</span>
              <span className="org-detail-value">
                {nodes.reduce((sum, n) => sum + (n.camera_count || 0), 0)}
              </span>
            </div>
          </div>
          <div className="org-card-id">
            <span className="org-detail-label">Org ID</span>
            <code>{organization?.id || "Unknown"}</code>
          </div>
        </div>
      </div>

      {recording && (
        <div className="settings-section">
          <h2>Recording</h2>
          <p className="section-description">
            Configure recording behavior for your camera nodes. Recordings are saved locally on each node.
          </p>
          <div className="settings-toggles">
            <label className="toggle-row">
              <div className="toggle-info">
                <span className="toggle-label">Continuous 24/7</span>
                <span className="toggle-desc">Record all cameras around the clock</span>
              </div>
              <button
                className={`toggle-switch ${recording.continuous_24_7 ? "active" : ""}`}
                onClick={() => handleRecordingToggle("continuous_24_7")}
                disabled={settingsSaving}
              >
                <span className="toggle-knob" />
              </button>
            </label>

            <label className="toggle-row">
              <div className="toggle-info">
                <span className="toggle-label">Scheduled Recording</span>
                <span className="toggle-desc">Only record during specific hours</span>
              </div>
              <button
                className={`toggle-switch ${recording.scheduled_recording ? "active" : ""}`}
                onClick={() => handleRecordingToggle("scheduled_recording")}
                disabled={settingsSaving}
              >
                <span className="toggle-knob" />
              </button>
            </label>

            {recording.scheduled_recording && (
              <div className="schedule-row">
                <div className="schedule-field">
                  <label>Start</label>
                  <input
                    type="time"
                    value={recording.scheduled_start}
                    onChange={(e) => handleRecordingChange("scheduled_start", e.target.value)}
                    disabled={settingsSaving}
                    className="settings-time-input"
                  />
                </div>
                <span className="schedule-separator">to</span>
                <div className="schedule-field">
                  <label>End</label>
                  <input
                    type="time"
                    value={recording.scheduled_end}
                    onChange={(e) => handleRecordingChange("scheduled_end", e.target.value)}
                    disabled={settingsSaving}
                    className="settings-time-input"
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {notifications && (
        <div className="settings-section">
          <h2>Notifications</h2>
          <p className="section-description">
            Choose which events show up in the bell inbox. Underlying motion
            events still record to history for incidents and analytics —
            turning a toggle off just stops the notification from appearing.
          </p>
          <div className="settings-toggles">
            <label className="toggle-row">
              <div className="toggle-info">
                <span className="toggle-label">Motion detection</span>
                <span className="toggle-desc">
                  Alert when a camera detects scene changes above its threshold
                </span>
              </div>
              <button
                type="button"
                className={`toggle-switch ${notifications.motion_notifications ? "active" : ""}`}
                onClick={() => handleNotificationToggle("motion_notifications")}
                disabled={notificationsSaving}
                aria-label="Toggle motion detection notifications"
                aria-pressed={notifications.motion_notifications}
              >
                <span className="toggle-knob" />
              </button>
            </label>
          </div>
        </div>
      )}

      {planInfo && (
        <div className="settings-section">
          <h2>Subscription</h2>
          <div className="plan-card">
            <div className="plan-card-header">
              <div className="plan-name-row">
                <h3>{planInfo.plan_name} Plan</h3>
                <span className={`plan-badge plan-badge-${planInfo.plan}`}>
                  {planInfo.plan === "free_org" ? "Free" : planInfo.plan_name}
                </span>
              </div>
              {planInfo.plan === "free_org" && (
                <Link to="/pricing" className="btn btn-primary btn-small">
                  Upgrade
                </Link>
              )}
              {planInfo.plan === "pro" && (
                <Link to="/pricing" className="btn btn-secondary btn-small">
                  Manage Plan
                </Link>
              )}
              {(planInfo.plan === "pro_plus" || planInfo.plan === "business") && (
                <Link to="/pricing" className="btn btn-secondary btn-small">
                  Manage Plan
                </Link>
              )}
            </div>
            <div className="plan-usage">
              <div className="usage-item">
                <div className="usage-label">
                  <span>Cameras</span>
                  <span className="usage-count">
                    {planInfo.usage.cameras} / {planInfo.limits.max_cameras >= 999 ? "Unlimited" : planInfo.limits.max_cameras}
                  </span>
                </div>
                <div className="usage-bar">
                  <div
                    className={`usage-fill ${planInfo.usage.cameras >= planInfo.limits.max_cameras ? "usage-full" : ""}`}
                    style={{ width: `${Math.min(100, (planInfo.usage.cameras / planInfo.limits.max_cameras) * 100)}%` }}
                  />
                </div>
              </div>
              <div className="usage-item">
                <div className="usage-label">
                  <span>Nodes</span>
                  <span className="usage-count">
                    {planInfo.usage.nodes} / {planInfo.limits.max_nodes >= 999 ? "Unlimited" : planInfo.limits.max_nodes}
                  </span>
                </div>
                <div className="usage-bar">
                  <div
                    className={`usage-fill ${planInfo.usage.nodes >= planInfo.limits.max_nodes ? "usage-full" : ""}`}
                    style={{ width: `${Math.min(100, (planInfo.usage.nodes / Math.min(planInfo.limits.max_nodes, 50)) * 100)}%` }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <WebhookSettings
        planInfo={planInfo}
        onUpgrade={() => setUpgradeFeature("webhooks")}
        showToast={showToast}
      />

      <div className="settings-section danger-zone">
        <h2>Danger Zone</h2>
        <p className="section-description">
          Irreversible actions that affect your entire organization.
        </p>

        {planInfo && !planInfo.features?.includes("admin") ? (
          <div className="danger-locked">
            <div className="locked-icon">🔒</div>
            <p>Danger zone actions require a <strong>Pro</strong> or <strong>Pro Plus</strong> plan.</p>
            <button
              className="btn btn-primary btn-small"
              onClick={() => setUpgradeFeature("danger-zone")}
            >
              Upgrade
            </button>
          </div>
        ) : (
        <div className="danger-actions">
          <div className="danger-item">
            <div className="danger-info">
              <h3>Wipe All Logs</h3>
              <p>Delete all stream access logs, MCP activity logs, and usage statistics.</p>
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
        )}

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
                            <li>{dangerResult.logs_deleted} stream log(s) deleted</li>
                            <li>{dangerResult.mcp_logs_deleted || 0} MCP log(s) deleted</li>
                            <li>{dangerResult.settings_deleted} setting(s) reset</li>
                          </ul>
                        )}
                        {dangerResult.deleted_logs !== undefined && (
                          <ul className="danger-summary">
                            <li>{dangerResult.deleted_logs} stream log(s) deleted</li>
                            {dangerResult.deleted_mcp_logs > 0 && (
                              <li>{dangerResult.deleted_mcp_logs} MCP activity log(s) deleted</li>
                            )}
                          </ul>
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

      <UpgradeModal
        isOpen={!!upgradeFeature}
        onClose={() => setUpgradeFeature(null)}
        feature={upgradeFeature}
        currentPlan={planInfo?.plan}
      />
    </div>
  )
}

export default SettingsPage
