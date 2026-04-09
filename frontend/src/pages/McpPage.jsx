import { useState, useEffect, useRef, useCallback } from "react"
import { useAuth, useOrganization } from "@clerk/clerk-react"
import {
  getMcpKeys, createMcpKey, revokeMcpKey, getPlanInfo,
  getMcpActivity, getMcpSessions, getMcpStats,
} from "../services/api"
import { useToasts } from "../hooks/useToasts.jsx"
import UpgradeModal from "../components/UpgradeModal.jsx"

const MCP_URL = `${window.location.origin}/mcp`
const API_URL = import.meta.env.VITE_API_URL || ""

const TOOLS = [
  { name: "view_camera", desc: "See what a camera sees — returns a live JPEG snapshot", highlight: true },
  { name: "watch_camera", desc: "Take multiple snapshots over time to observe activity", highlight: true },
  { name: "list_cameras", desc: "List all cameras with status and codec info" },
  { name: "get_camera", desc: "Get details for a specific camera" },
  { name: "get_stream_url", desc: "Get a temporary HLS stream URL" },
  { name: "list_nodes", desc: "List camera nodes with status" },
  { name: "get_node", desc: "Get details for a specific node" },
  { name: "list_camera_groups", desc: "List camera groups" },
  { name: "create_camera_group", desc: "Create a new camera group" },
  { name: "assign_camera_to_group", desc: "Assign a camera to a group" },
  { name: "get_recording_settings", desc: "View current recording config" },
  { name: "update_recording_settings", desc: "Change recording settings" },
  { name: "get_stream_logs", desc: "View stream access history" },
  { name: "get_stream_stats", desc: "Get aggregated stream statistics" },
  { name: "get_system_status", desc: "System overview: cameras, nodes, plan" },
]

// Status colors for tool call events
const STATUS_COLORS = {
  completed: "var(--accent-green)",
  error: "var(--accent-red)",
  started: "var(--accent-amber)",
}

function formatTimeAgo(seconds) {
  if (seconds < 5) return "just now"
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return `${Math.floor(seconds / 3600)}h ago`
}

function formatTimestamp(ts) {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

function McpPage() {
  const { getToken } = useAuth()
  const { organization } = useOrganization()
  const { showToast } = useToasts()

  // Plan & auth
  const [planInfo, setPlanInfo] = useState(null)

  // Live activity
  const [events, setEvents] = useState([])
  const [sessions, setSessions] = useState([])
  const [stats, setStats] = useState(null)
  const [sseConnected, setSseConnected] = useState(false)
  const eventSourceRef = useRef(null)
  const eventsEndRef = useRef(null)

  // Key management (collapsible)
  const [showKeys, setShowKeys] = useState(false)
  const [showTools, setShowTools] = useState(false)
  const [showConfig, setShowConfig] = useState(false)
  const [keys, setKeys] = useState([])
  const [keysLoading, setKeysLoading] = useState(false)
  const [newKeyName, setNewKeyName] = useState("")
  const [createdKey, setCreatedKey] = useState(null)
  const [creating, setCreating] = useState(false)
  const [copied, setCopied] = useState(null)
  const [revoking, setRevoking] = useState(null)
  const [showUpgrade, setShowUpgrade] = useState(false)

  // Load plan info
  useEffect(() => {
    if (organization) loadPlanInfo()
  }, [organization])

  const loadPlanInfo = async () => {
    try {
      const token = await getToken()
      const data = await getPlanInfo(() => Promise.resolve(token))
      setPlanInfo(data)
    } catch (err) {
      console.error("Failed to load plan info:", err)
    }
  }

  // Load initial activity data + start polling
  useEffect(() => {
    if (!organization || !planInfo?.features?.includes("admin")) return

    loadActivity()
    loadSessions()
    loadStats()

    // Poll sessions and stats every 10s
    const interval = setInterval(() => {
      loadSessions()
      loadStats()
    }, 10000)

    return () => clearInterval(interval)
  }, [organization, planInfo])

  // SSE stream for real-time events
  useEffect(() => {
    if (!organization || !planInfo?.features?.includes("admin")) return

    let cancelled = false
    let reader = null

    const connectSSE = async () => {
      try {
        const token = await getToken()
        const response = await fetch(`${API_URL}/api/mcp/activity/stream`, {
          headers: { Authorization: `Bearer ${token}` },
        })

        if (!response.ok || cancelled) return

        setSseConnected(true)
        reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ""

        while (!cancelled) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split("\n")
          buffer = lines.pop() || ""

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6))
                if (data.type === "tool_call") {
                  setEvents(prev => {
                    const next = [...prev, data]
                    // Keep last 100 events
                    return next.length > 100 ? next.slice(-100) : next
                  })
                }
              } catch { /* ignore parse errors */ }
            }
          }
        }
      } catch (err) {
        if (!cancelled) {
          console.error("[MCP SSE] Connection error:", err)
          setSseConnected(false)
          // Reconnect after 5s
          setTimeout(() => { if (!cancelled) connectSSE() }, 5000)
        }
      }
    }

    connectSSE()

    return () => {
      cancelled = true
      setSseConnected(false)
      if (reader) reader.cancel().catch(() => {})
    }
  }, [organization, planInfo])

  // Auto-scroll event feed
  useEffect(() => {
    if (eventsEndRef.current) {
      eventsEndRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [events])

  const loadActivity = async () => {
    try {
      const token = await getToken()
      const data = await getMcpActivity(() => Promise.resolve(token), 50)
      setEvents(data.map(e => ({ ...e, type: "tool_call" })))
    } catch (err) {
      console.error("Failed to load activity:", err)
    }
  }

  const loadSessions = async () => {
    try {
      const token = await getToken()
      const data = await getMcpSessions(() => Promise.resolve(token))
      setSessions(data)
    } catch (err) {
      console.error("Failed to load sessions:", err)
    }
  }

  const loadStats = async () => {
    try {
      const token = await getToken()
      const data = await getMcpStats(() => Promise.resolve(token))
      setStats(data)
    } catch (err) {
      console.error("Failed to load stats:", err)
    }
  }

  // Key management functions
  const loadKeys = async () => {
    setKeysLoading(true)
    try {
      const token = await getToken()
      const data = await getMcpKeys(() => Promise.resolve(token))
      setKeys(data)
    } catch (err) {
      console.error("Failed to load MCP keys:", err)
    } finally {
      setKeysLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!newKeyName.trim()) return
    setCreating(true)
    try {
      const token = await getToken()
      const data = await createMcpKey(() => Promise.resolve(token), newKeyName.trim())
      setCreatedKey(data.key)
      setNewKeyName("")
      await loadKeys()
      showToast("MCP API key created", "success")
    } catch (err) {
      showToast(err.message || "Failed to create key", "error")
    } finally {
      setCreating(false)
    }
  }

  const handleRevoke = async (keyId) => {
    setRevoking(keyId)
    try {
      const token = await getToken()
      await revokeMcpKey(() => Promise.resolve(token), keyId)
      await loadKeys()
      showToast("API key revoked", "success")
    } catch (err) {
      showToast(err.message || "Failed to revoke key", "error")
    } finally {
      setRevoking(null)
    }
  }

  const copyToClipboard = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(label)
      showToast("Copied to clipboard", "success")
      setTimeout(() => setCopied(null), 2000)
    } catch {
      showToast("Failed to copy", "error")
    }
  }

  const configJson = (key) => JSON.stringify({
    mcpServers: {
      opensentry: {
        type: "http",
        url: MCP_URL,
        headers: {
          Authorization: `Bearer ${key || "osc_your_key_here"}`
        }
      }
    }
  }, null, 2)

  const isPro = planInfo?.features?.includes("admin")

  if (!organization) {
    return (
      <div className="mcp-container">
        <h1 className="page-title">MCP Integration</h1>
        <p className="text-muted">Please select an organization.</p>
      </div>
    )
  }

  // Locked gate for non-pro
  if (planInfo && !isPro) {
    return (
      <div className="mcp-container">
        <h1 className="page-title">MCP Integration</h1>
        <div className="mcp-locked-page">
          <div className="mcp-glow mcp-glow-1" />
          <div className="mcp-glow mcp-glow-2" />
          <div className="mcp-locked-hero">
            <div className="mcp-locked-badge">PRO</div>
            <div className="mcp-locked-icon">{"</>"}</div>
            <h2>AI-Powered Camera Control</h2>
            <p>
              Give Claude Code, Cursor, or any MCP-compatible AI tool direct
              access to your cameras, nodes, and settings — all through
              natural language.
            </p>
            <div className="mcp-locked-examples">
              <div className="mcp-example">"Show me what the front door camera sees"</div>
              <div className="mcp-example">"Watch the garage cam for 30 seconds"</div>
              <div className="mcp-example">"List all my cameras and their status"</div>
            </div>
            <button className="mcp-upgrade-btn" onClick={() => setShowUpgrade(true)}>
              Unlock MCP Integration
            </button>
            <span className="mcp-upgrade-hint">Available on Pro and Business plans</span>
          </div>
          <div className="mcp-locked-tools">
            <h3><span>{TOOLS.length}</span> tools included with Pro</h3>
            <div className="mcp-tools-grid">
              {TOOLS.map((tool) => (
                <div key={tool.name} className={`mcp-tool-card mcp-tool-locked${tool.highlight ? " mcp-tool-visual" : ""}`}>
                  <code>{tool.name}</code>
                  <span>{tool.desc}</span>
                  {tool.highlight && <span className="mcp-tool-badge">VISUAL</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
        <UpgradeModal isOpen={showUpgrade} onClose={() => setShowUpgrade(false)} feature="mcp" currentPlan={planInfo?.plan} />
      </div>
    )
  }

  return (
    <div className="mcp-dashboard">
      {/* Header */}
      <div className="mcp-dash-header">
        <div className="mcp-dash-title-row">
          <div className="mcp-dash-title-left">
            <div className="mcp-dash-icon">{"</>"}</div>
            <div>
              <h1 className="mcp-dash-title">MCP Control Center</h1>
              <p className="mcp-dash-subtitle">Real-time AI tool activity monitor</p>
            </div>
          </div>
          <div className="mcp-dash-live-badge">
            <span className={`mcp-live-dot ${sseConnected ? "connected" : "disconnected"}`} />
            <span>{sseConnected ? "LIVE" : "CONNECTING"}</span>
          </div>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="mcp-stats-bar">
        <div className="mcp-stat-item">
          <div className="mcp-stat-value accent-green">{stats?.active_clients ?? 0}</div>
          <div className="mcp-stat-label">Connected Clients</div>
        </div>
        <div className="mcp-stat-item">
          <div className="mcp-stat-value accent-blue">{stats?.calls_per_min ?? 0}</div>
          <div className="mcp-stat-label">Calls / min</div>
        </div>
        <div className="mcp-stat-item">
          <div className="mcp-stat-value accent-cyan">{stats?.total_calls ?? 0}</div>
          <div className="mcp-stat-label">Total Calls</div>
        </div>
        <div className="mcp-stat-item">
          <div className={`mcp-stat-value ${stats?.error_count > 0 ? "accent-red" : "accent-green"}`}>
            {stats?.error_count ?? 0}
          </div>
          <div className="mcp-stat-label">Errors</div>
        </div>
      </div>

      {/* Main Grid: Activity Feed + Clients Sidebar */}
      <div className="mcp-dash-grid">
        {/* Live Activity Feed — Center */}
        <div className="mcp-activity-panel">
          <div className="mcp-panel-header">
            <h2>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
              </svg>
              Live Activity
            </h2>
            <span className="mcp-event-count">{events.length} events</span>
          </div>
          <div className="mcp-activity-feed">
            {events.length === 0 ? (
              <div className="mcp-feed-empty">
                <div className="mcp-feed-empty-icon">
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.3">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                  </svg>
                </div>
                <p>Waiting for MCP tool calls...</p>
                <span>Connect an AI tool to see live activity here</span>
              </div>
            ) : (
              <>
                {events.map((event, i) => (
                  <div
                    key={event.id + "-" + i}
                    className={`mcp-event-row mcp-event-${event.status} mcp-event-enter`}
                  >
                    <div className="mcp-event-time">{formatTimestamp(event.timestamp)}</div>
                    <div className="mcp-event-status-dot" style={{ background: STATUS_COLORS[event.status] }} />
                    <div className="mcp-event-tool">{event.tool_name}</div>
                    {event.args_summary && (
                      <div className="mcp-event-args">{event.args_summary}</div>
                    )}
                    <div className="mcp-event-meta">
                      <span className="mcp-event-client">{event.key_name}</span>
                      {event.duration_ms != null && (
                        <span className="mcp-event-duration">{event.duration_ms}ms</span>
                      )}
                    </div>
                    {event.error && (
                      <div className="mcp-event-error">{event.error}</div>
                    )}
                  </div>
                ))}
                <div ref={eventsEndRef} />
              </>
            )}
          </div>
        </div>

        {/* Connected Clients Sidebar */}
        <div className="mcp-clients-panel">
          <div className="mcp-panel-header">
            <h2>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4-4v2"/>
                <circle cx="9" cy="7" r="4"/>
                <path d="M23 21v-2a4 4 0 00-3-3.87"/>
                <path d="M16 3.13a4 4 0 010 7.75"/>
              </svg>
              Clients
            </h2>
            <span className="mcp-client-count">{sessions.length}</span>
          </div>
          <div className="mcp-clients-list">
            {sessions.length === 0 ? (
              <div className="mcp-clients-empty">
                <p>No active clients</p>
              </div>
            ) : (
              sessions.map((session, i) => (
                <div key={session.key_name + i} className={`mcp-client-card mcp-client-${session.status}`}>
                  <div className="mcp-client-header">
                    <span className={`mcp-client-dot mcp-client-dot-${session.status}`} />
                    <span className="mcp-client-name">{session.key_name}</span>
                  </div>
                  <div className="mcp-client-info">
                    <span>{session.call_count} calls</span>
                    <span>{formatTimeAgo(session.last_active_ago)}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Collapsible Sections */}
      <div className="mcp-collapsible-sections">
        {/* API Keys */}
        <div className="mcp-collapse-section">
          <button
            className={`mcp-collapse-toggle ${showKeys ? "open" : ""}`}
            onClick={() => { setShowKeys(!showKeys); if (!showKeys && keys.length === 0) loadKeys() }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
            </svg>
            API Keys
            <svg className="mcp-collapse-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
          {showKeys && (
            <div className="mcp-collapse-body">
              {createdKey && (
                <div className="mcp-key-created">
                  <div className="mcp-key-created-header">
                    <span className="mcp-key-created-icon">🔑</span>
                    <strong>Key created — save it now!</strong>
                  </div>
                  <p className="mcp-key-warning">This is the only time you'll see this key. Copy it before closing.</p>
                  <div className="mcp-key-display">
                    <code>{createdKey}</code>
                    <button className="btn btn-small btn-secondary" onClick={() => copyToClipboard(createdKey, "key")}>
                      {copied === "key" ? "Copied!" : "Copy Key"}
                    </button>
                  </div>
                  <button className="btn btn-small btn-secondary mcp-key-dismiss" onClick={() => setCreatedKey(null)}>
                    I've saved it
                  </button>
                </div>
              )}
              <div className="mcp-key-create">
                <input
                  type="text"
                  placeholder="Key name (e.g. 'Claude Code')"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  className="mcp-key-input"
                />
                <button className="btn btn-primary" onClick={handleCreate} disabled={creating || !newKeyName.trim()}>
                  {creating ? "Creating..." : "Generate Key"}
                </button>
              </div>
              {keysLoading ? (
                <div className="loading-spinner" />
              ) : keys.length > 0 ? (
                <div className="mcp-keys-list">
                  {keys.map((k) => (
                    <div key={k.id} className="mcp-key-item">
                      <div className="mcp-key-info">
                        <span className="mcp-key-name">{k.name}</span>
                        <span className="mcp-key-meta">
                          Created {new Date(k.created_at).toLocaleDateString()}
                          {k.last_used_at && <> — Last used {new Date(k.last_used_at).toLocaleDateString()}</>}
                        </span>
                      </div>
                      <button className="btn btn-small btn-danger" onClick={() => handleRevoke(k.id)} disabled={revoking === k.id}>
                        {revoking === k.id ? "Revoking..." : "Revoke"}
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted mcp-no-keys">No API keys yet. Generate one above to get started.</p>
              )}
            </div>
          )}
        </div>

        {/* Connection Config */}
        <div className="mcp-collapse-section">
          <button
            className={`mcp-collapse-toggle ${showConfig ? "open" : ""}`}
            onClick={() => setShowConfig(!showConfig)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
              <line x1="8" y1="21" x2="16" y2="21"/>
              <line x1="12" y1="17" x2="12" y2="21"/>
            </svg>
            Connection Config
            <svg className="mcp-collapse-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
          {showConfig && (
            <div className="mcp-collapse-body">
              <p className="section-description">
                Add this to your Claude Code settings (<code>~/.claude.json</code>) or project <code>.mcp.json</code>:
              </p>
              <div className="mcp-config-block">
                <div className="mcp-config-header">
                  <span>Claude Code / .mcp.json</span>
                  <button className="btn btn-small btn-secondary" onClick={() => copyToClipboard(configJson(createdKey), "config")}>
                    {copied === "config" ? "Copied!" : "Copy"}
                  </button>
                </div>
                <pre className="mcp-config-code">{configJson(createdKey)}</pre>
              </div>
              <p className="mcp-config-hint">
                Or add via CLI: <code>claude mcp add --transport http opensentry {MCP_URL} --header "Authorization: Bearer osc_your_key"</code>
              </p>
            </div>
          )}
        </div>

        {/* Available Tools */}
        <div className="mcp-collapse-section">
          <button
            className={`mcp-collapse-toggle ${showTools ? "open" : ""}`}
            onClick={() => setShowTools(!showTools)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>
            </svg>
            Available Tools ({TOOLS.length})
            <svg className="mcp-collapse-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
          {showTools && (
            <div className="mcp-collapse-body">
              <div className="mcp-tools-grid">
                {TOOLS.map((tool) => (
                  <div key={tool.name} className={`mcp-tool-card${tool.highlight ? " mcp-tool-visual" : ""}`}>
                    <code>{tool.name}</code>
                    <span>{tool.desc}</span>
                    {tool.highlight && <span className="mcp-tool-badge">VISUAL</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <UpgradeModal isOpen={showUpgrade} onClose={() => setShowUpgrade(false)} feature="mcp" currentPlan={planInfo?.plan} />
    </div>
  )
}

export default McpPage
