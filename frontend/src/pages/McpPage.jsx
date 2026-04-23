import { useState, useEffect, useRef, useCallback } from "react"
import { useAuth, useOrganization } from "@clerk/clerk-react"
import {
  getMcpKeys, createMcpKey, revokeMcpKey,
  getMcpActivity, getMcpSessions, getMcpStats,
  getIncidents, getIncidentCounts, getMcpToolCatalog,
} from "../services/api"
import { useToasts } from "../hooks/useToasts.jsx"
import { usePlanInfo } from "../hooks/usePlanInfo.jsx"
import UpgradeModal from "../components/UpgradeModal.jsx"
import IncidentReportModal from "../components/IncidentReportModal.jsx"

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
  { name: "get_recording_settings", desc: "View current recording config" },
  { name: "get_stream_logs", desc: "View stream access history" },
  { name: "get_stream_stats", desc: "Get aggregated stream statistics" },
  { name: "get_system_status", desc: "System overview: cameras, nodes, plan" },
  { name: "create_incident", desc: "Open a new AI-authored incident report", write: true },
  { name: "add_observation", desc: "Append a text observation to an incident", write: true },
  { name: "attach_snapshot", desc: "Capture a snapshot and attach it as evidence", write: true },
  { name: "update_incident", desc: "Change an incident's status, severity, or summary", write: true },
  { name: "finalize_incident", desc: "Write the long-form incident report", write: true },
]

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 }
const STATUS_LABELS = {
  open: "Open",
  acknowledged: "Acknowledged",
  resolved: "Resolved",
  dismissed: "Dismissed",
}

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
  const { planInfo } = usePlanInfo()

  // Live activity
  const [events, setEvents] = useState([])
  const [sessions, setSessions] = useState([])
  const [stats, setStats] = useState(null)
  const [sseConnected, setSseConnected] = useState(false)
  const eventSourceRef = useRef(null)
  const eventsEndRef = useRef(null)

  // AI incident reports
  const [incidents, setIncidents] = useState([])
  const [incidentCounts, setIncidentCountsState] = useState({ open: 0, open_critical: 0, open_high: 0, total: 0 })
  const [incidentFilter, setIncidentFilter] = useState("open") // "open" | "all"
  const [openIncidentId, setOpenIncidentId] = useState(null)

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

  // Per-key tool scoping — "all" | "readonly" | "custom"
  const [scopeMode, setScopeMode] = useState("all")
  const [scopeTools, setScopeTools] = useState([])
  const [toolCatalog, setToolCatalog] = useState(null)
  const [catalogLoading, setCatalogLoading] = useState(false)

  // Connection config
  const [setupOs, setSetupOs] = useState(() => {
    const ua = navigator.userAgent.toLowerCase()
    if (ua.includes("win")) return "windows"
    if (ua.includes("mac")) return "macos"
    return "linux"
  })
  const [configTab, setConfigTab] = useState("auto")
  // Lets returning users paste a saved key so commands/configs render with
  // real credentials instead of the `osc_your_key_here` placeholder.
  const [pastedKey, setPastedKey] = useState("")

  // Load initial activity data + start polling
  useEffect(() => {
    if (!organization || !planInfo?.features?.includes("admin")) return

    loadActivity()
    loadSessions()
    loadStats()
    loadIncidents()
    loadIncidentCounts()

    // Poll sessions, stats, and incidents every 10s
    const interval = setInterval(() => {
      loadSessions()
      loadStats()
      loadIncidents()
      loadIncidentCounts()
    }, 10000)

    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organization, planInfo, incidentFilter])

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

  const loadIncidents = async () => {
    try {
      const token = await getToken()
      const params = { limit: 50 }
      if (incidentFilter === "open") params.status = "open"
      const data = await getIncidents(() => Promise.resolve(token), params)
      // Sort by severity (critical first) then by created_at desc — already desc from API
      const sorted = [...(data.incidents || [])].sort((a, b) => {
        const sa = SEVERITY_ORDER[a.severity] ?? 9
        const sb = SEVERITY_ORDER[b.severity] ?? 9
        if (sa !== sb) return sa - sb
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      })
      setIncidents(sorted)
    } catch (err) {
      console.error("Failed to load incidents:", err)
    }
  }

  const loadIncidentCounts = async () => {
    try {
      const token = await getToken()
      const data = await getIncidentCounts(() => Promise.resolve(token))
      setIncidentCountsState(data)
    } catch (err) {
      console.error("Failed to load incident counts:", err)
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

  const loadToolCatalog = async () => {
    if (toolCatalog || catalogLoading) return
    setCatalogLoading(true)
    try {
      const token = await getToken()
      const data = await getMcpToolCatalog(() => Promise.resolve(token))
      setToolCatalog(data)
    } catch (err) {
      console.error("Failed to load tool catalog:", err)
      showToast("Failed to load tool list", "error")
    } finally {
      setCatalogLoading(false)
    }
  }

  const handleScopeModeChange = (mode) => {
    setScopeMode(mode)
    if (mode === "custom") {
      loadToolCatalog()
      // Seed custom selection with read tools when switching in with an empty set —
      // gives users a sensible starting point without forcing click-everything.
      if (scopeTools.length === 0 && toolCatalog) {
        setScopeTools(toolCatalog.read.map((t) => t.name))
      }
    }
  }

  const toggleScopeTool = (name) => {
    setScopeTools((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
    )
  }

  const handleCreate = async () => {
    if (!newKeyName.trim()) return
    if (scopeMode === "custom" && scopeTools.length === 0) {
      showToast("Select at least one tool for custom scope", "error")
      return
    }
    setCreating(true)
    try {
      const token = await getToken()
      const data = await createMcpKey(
        () => Promise.resolve(token),
        {
          name: newKeyName.trim(),
          scopeMode,
          scopeTools: scopeMode === "custom" ? scopeTools : null,
        }
      )
      setCreatedKey(data.key)
      setNewKeyName("")
      setScopeMode("all")
      setScopeTools([])
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

  // Priority: just-created key → user-pasted key → placeholder. The placeholder
  // only renders when the user hasn't offered anything — we warn them about it
  // in the UI so they don't copy a dead command.
  const trimmedPasted = pastedKey.trim()
  const activeKey = createdKey || trimmedPasted || "osc_your_key_here"
  const hasRealKey = Boolean(createdKey || trimmedPasted)
  const base = window.location.origin

  // Per-client config generators
  const clientConfigs = {
    "claude-code": {
      label: "Claude Code",
      file: "~/.claude.json or .mcp.json",
      config: JSON.stringify({ mcpServers: { opensentry: { type: "http", url: MCP_URL, headers: { Authorization: `Bearer ${activeKey}` } } } }, null, 2),
      cli: `claude mcp add --transport http opensentry ${MCP_URL} --header "Authorization: Bearer ${activeKey}"`,
    },
    "claude-desktop": {
      label: "Claude Desktop",
      file: setupOs === "macos" ? "~/Library/Application Support/Claude/claude_desktop_config.json" : setupOs === "windows" ? "%APPDATA%\\Claude\\claude_desktop_config.json" : "~/.config/Claude/claude_desktop_config.json",
      config: JSON.stringify({ mcpServers: { opensentry: { type: "http", url: MCP_URL, headers: { Authorization: `Bearer ${activeKey}` } } } }, null, 2),
    },
    cursor: {
      label: "Cursor",
      file: "~/.cursor/mcp.json",
      config: JSON.stringify({ mcpServers: { opensentry: { url: MCP_URL, headers: { Authorization: `Bearer ${activeKey}` } } } }, null, 2),
    },
    windsurf: {
      label: "Windsurf",
      file: "~/.codeium/windsurf/mcp_config.json",
      config: JSON.stringify({ mcpServers: { opensentry: { serverUrl: MCP_URL, headers: { Authorization: `Bearer ${activeKey}` } } } }, null, 2),
    },
  }

  // Windows: `iex -Args` is invalid (Invoke-Expression has no -Args parameter).
  // The scriptblock::Create pattern is the correct way to pipe-and-parameterize
  // a remote PowerShell script, and it matches what the script's param() expects.
  const autoSetupCmd = setupOs === "windows"
    ? `& ([scriptblock]::Create((irm ${base}/mcp-setup.ps1))) '${activeKey}' '${MCP_URL}'`
    : `curl -fsSL ${base}/mcp-setup.sh | bash -s -- ${activeKey} ${MCP_URL}`

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
            <span className="mcp-upgrade-hint">Available on Pro and Pro Plus plans</span>
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
      <div className="mcp-stats-bar mcp-stats-bar-5">
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
        <div className="mcp-stat-item">
          <div className={`mcp-stat-value ${incidentCounts.open > 0 ? "accent-red" : "accent-green"}`}>
            {incidentCounts.open ?? 0}
          </div>
          <div className="mcp-stat-label">Open Incidents</div>
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

      {/* AI Incident Reports */}
      <div className="mcp-incidents-panel">
        <div className="mcp-panel-header mcp-incidents-header">
          <h2>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            AI Incident Reports
          </h2>
          <div className="mcp-incidents-controls">
            <button
              className={`mcp-incidents-filter ${incidentFilter === "open" ? "active" : ""}`}
              onClick={() => setIncidentFilter("open")}
            >
              Open ({incidentCounts.open})
            </button>
            <button
              className={`mcp-incidents-filter ${incidentFilter === "all" ? "active" : ""}`}
              onClick={() => setIncidentFilter("all")}
            >
              All ({incidentCounts.total})
            </button>
          </div>
        </div>
        <div className="mcp-incidents-list">
          {incidents.length === 0 ? (
            <div className="mcp-incidents-empty">
              <div className="mcp-incidents-empty-icon">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.3">
                  <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
                  <polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
              </div>
              <p>{incidentFilter === "open" ? "No open incidents" : "No incidents yet"}</p>
              <span>Reports filed by your AI agent will appear here</span>
            </div>
          ) : (
            incidents.map((incident) => (
              <button
                key={incident.id}
                className={`mcp-incident-row mcp-incident-${incident.severity} mcp-incident-status-${incident.status}`}
                onClick={() => setOpenIncidentId(incident.id)}
              >
                <span className={`mcp-incident-sev-dot mcp-incident-sev-${incident.severity}`} />
                <span className="mcp-incident-time">
                  {new Date(incident.created_at).toLocaleString([], {
                    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
                  })}
                </span>
                <span className="mcp-incident-camera">
                  {incident.camera_id || "—"}
                </span>
                <span className="mcp-incident-title">{incident.title}</span>
                <span className={`mcp-incident-status mcp-incident-status-badge-${incident.status}`}>
                  {STATUS_LABELS[incident.status] || incident.status}
                </span>
                {incident.evidence_count > 0 && (
                  <span className="mcp-incident-evidence-count">
                    {incident.evidence_count} evidence
                  </span>
                )}
              </button>
            ))
          )}
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
                  onKeyDown={(e) => e.key === "Enter" && scopeMode !== "custom" && handleCreate()}
                  className="mcp-key-input"
                />
                <button className="btn btn-primary" onClick={handleCreate} disabled={creating || !newKeyName.trim() || (scopeMode === "custom" && scopeTools.length === 0)}>
                  {creating ? "Creating..." : "Generate Key"}
                </button>
              </div>
              <div className="mcp-scope-picker">
                <div className="mcp-scope-picker-header">
                  <span className="mcp-scope-picker-label">Tool access</span>
                  <span className="mcp-scope-picker-help">Limit which MCP tools this key can call.</span>
                </div>
                <div className="mcp-scope-options">
                  <label className={`mcp-scope-option ${scopeMode === "all" ? "active" : ""}`}>
                    <input
                      type="radio"
                      name="scope-mode"
                      value="all"
                      checked={scopeMode === "all"}
                      onChange={() => handleScopeModeChange("all")}
                    />
                    <div className="mcp-scope-option-content">
                      <span className="mcp-scope-option-title">All tools</span>
                      <span className="mcp-scope-option-desc">Full access — reads and writes.</span>
                    </div>
                  </label>
                  <label className={`mcp-scope-option ${scopeMode === "readonly" ? "active" : ""}`}>
                    <input
                      type="radio"
                      name="scope-mode"
                      value="readonly"
                      checked={scopeMode === "readonly"}
                      onChange={() => handleScopeModeChange("readonly")}
                    />
                    <div className="mcp-scope-option-content">
                      <span className="mcp-scope-option-title">Read-only</span>
                      <span className="mcp-scope-option-desc">Agent can look but can't modify incidents.</span>
                    </div>
                  </label>
                  <label className={`mcp-scope-option ${scopeMode === "custom" ? "active" : ""}`}>
                    <input
                      type="radio"
                      name="scope-mode"
                      value="custom"
                      checked={scopeMode === "custom"}
                      onChange={() => handleScopeModeChange("custom")}
                    />
                    <div className="mcp-scope-option-content">
                      <span className="mcp-scope-option-title">Custom</span>
                      <span className="mcp-scope-option-desc">Pick exactly which tools this key may use.</span>
                    </div>
                  </label>
                </div>
                {scopeMode === "custom" && (
                  <div className="mcp-scope-custom">
                    {catalogLoading && <div className="loading-spinner" />}
                    {!catalogLoading && toolCatalog && (
                      <>
                        {[
                          { key: "read", label: "Read tools", group: toolCatalog.read },
                          { key: "write", label: "Write tools", group: toolCatalog.write },
                        ].map(({ key, label, group }) => {
                          const allNames = group.map((t) => t.name)
                          const allChecked = allNames.every((n) => scopeTools.includes(n))
                          const someChecked = allNames.some((n) => scopeTools.includes(n))
                          const toggleGroup = () => {
                            setScopeTools((prev) => {
                              if (allChecked) return prev.filter((n) => !allNames.includes(n))
                              return [...new Set([...prev, ...allNames])]
                            })
                          }
                          return (
                            <div key={key} className="mcp-scope-group">
                              <div className="mcp-scope-group-header">
                                <label className="mcp-scope-group-toggle">
                                  <input
                                    type="checkbox"
                                    checked={allChecked}
                                    ref={(el) => { if (el) el.indeterminate = !allChecked && someChecked }}
                                    onChange={toggleGroup}
                                  />
                                  <span className="mcp-scope-group-label">{label}</span>
                                  <span className="mcp-scope-group-count">
                                    {group.filter((t) => scopeTools.includes(t.name)).length} / {group.length}
                                  </span>
                                </label>
                              </div>
                              <div className="mcp-scope-tool-grid">
                                {group.map((tool) => (
                                  <label key={tool.name} className={`mcp-scope-tool ${scopeTools.includes(tool.name) ? "active" : ""}`}>
                                    <input
                                      type="checkbox"
                                      checked={scopeTools.includes(tool.name)}
                                      onChange={() => toggleScopeTool(tool.name)}
                                    />
                                    <div className="mcp-scope-tool-body">
                                      <code className="mcp-scope-tool-name">{tool.name}</code>
                                      {tool.description && (
                                        <span className="mcp-scope-tool-desc">
                                          {tool.description.split("\n")[0].slice(0, 100)}
                                        </span>
                                      )}
                                    </div>
                                  </label>
                                ))}
                              </div>
                            </div>
                          )
                        })}
                        <div className="mcp-scope-summary">
                          <strong>{scopeTools.length}</strong> of {toolCatalog.total} tools selected
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
              {keysLoading ? (
                <div className="loading-spinner" />
              ) : keys.length > 0 ? (
                <div className="mcp-keys-list">
                  {keys.map((k) => {
                    const mode = k.scope_mode || "all"
                    const toolCount = Array.isArray(k.scope_tools) ? k.scope_tools.length : 0
                    const badgeText = mode === "all"
                      ? "All tools"
                      : mode === "readonly"
                        ? "Read-only"
                        : `${toolCount} tool${toolCount === 1 ? "" : "s"}`
                    return (
                      <div key={k.id} className="mcp-key-item">
                        <div className="mcp-key-info">
                          <div className="mcp-key-name-row">
                            <span className="mcp-key-name">{k.name}</span>
                            <span className={`mcp-scope-badge mcp-scope-badge-${mode}`} title={mode === "custom" ? k.scope_tools?.join(", ") : undefined}>
                              {badgeText}
                            </span>
                          </div>
                          <span className="mcp-key-meta">
                            Created {new Date(k.created_at).toLocaleDateString()}
                            {k.last_used_at && <> — Last used {new Date(k.last_used_at).toLocaleDateString()}</>}
                          </span>
                        </div>
                        <button className="btn btn-small btn-danger" onClick={() => handleRevoke(k.id)} disabled={revoking === k.id}>
                          {revoking === k.id ? "Revoking..." : "Revoke"}
                        </button>
                      </div>
                    )
                  })}
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
            Connect a Client
            <svg className="mcp-collapse-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
          {showConfig && (
            <div className="mcp-collapse-body">
              {/* Client tabs */}
              <div className="mcp-client-tabs">
                <button className={`mcp-client-tab ${configTab === "auto" ? "active" : ""}`} onClick={() => setConfigTab("auto")}>
                  Auto Setup
                </button>
                {Object.entries(clientConfigs).map(([key, c]) => (
                  <button key={key} className={`mcp-client-tab ${configTab === key ? "active" : ""}`} onClick={() => setConfigTab(key)}>
                    {c.label}
                  </button>
                ))}
              </div>

              {/* Active key banner — lets returning users paste their saved
                  key so every command and config below renders with real
                  credentials instead of the osc_your_key_here placeholder. */}
              {!createdKey && (
                <div className={`mcp-active-key ${hasRealKey ? "mcp-active-key-filled" : "mcp-active-key-empty"}`}>
                  <div className="mcp-active-key-header">
                    <span className="mcp-active-key-icon">{hasRealKey ? "✓" : "⚠"}</span>
                    <div>
                      <strong>
                        {hasRealKey ? "Using the key below in all commands" : "Paste a saved API key"}
                      </strong>
                      <p className="mcp-active-key-hint">
                        {hasRealKey
                          ? "Clear the field to revert to the placeholder. Keys are used locally only — never sent anywhere."
                          : "The commands below show a placeholder. Generate a key above, or paste an existing one to bake it into the copyable commands."}
                      </p>
                    </div>
                  </div>
                  <input
                    type="text"
                    className="mcp-active-key-input"
                    placeholder="osc_..."
                    value={pastedKey}
                    onChange={(e) => setPastedKey(e.target.value)}
                    spellCheck={false}
                    autoComplete="off"
                  />
                </div>
              )}

              {/* Auto Setup */}
              {configTab === "auto" && (
                <div className="mcp-setup-auto">
                  <p className="mcp-setup-desc">
                    Run this command to automatically detect and configure your MCP clients:
                  </p>
                  <div className="mcp-os-tabs">
                    {["linux", "macos", "windows"].map(os => (
                      <button key={os} className={`mcp-os-tab ${setupOs === os ? "active" : ""}`} onClick={() => setSetupOs(os)}>
                        {os === "macos" ? "macOS" : os.charAt(0).toUpperCase() + os.slice(1)}
                      </button>
                    ))}
                  </div>
                  <div className="mcp-config-block">
                    <div className="mcp-config-header">
                      <span>{setupOs === "windows" ? "PowerShell" : "Terminal"}</span>
                      <button className="btn btn-small btn-secondary" onClick={() => copyToClipboard(autoSetupCmd, "auto")}>
                        {copied === "auto" ? "Copied!" : "Copy"}
                      </button>
                    </div>
                    <pre className="mcp-config-code">{autoSetupCmd}</pre>
                  </div>
                  <p className="mcp-setup-note">
                    The script will scan for installed clients (Claude Code, Claude Desktop, Cursor, Windsurf) and let you choose which to configure.
                  </p>
                </div>
              )}

              {/* Per-client manual config */}
              {configTab !== "auto" && clientConfigs[configTab] && (
                <div className="mcp-setup-manual">
                  <p className="mcp-setup-desc">
                    Add this to <code>{clientConfigs[configTab].file}</code>:
                  </p>
                  <div className="mcp-config-block">
                    <div className="mcp-config-header">
                      <span>{clientConfigs[configTab].label}</span>
                      <button className="btn btn-small btn-secondary" onClick={() => copyToClipboard(clientConfigs[configTab].config, "client-config")}>
                        {copied === "client-config" ? "Copied!" : "Copy"}
                      </button>
                    </div>
                    <pre className="mcp-config-code">{clientConfigs[configTab].config}</pre>
                  </div>
                  {clientConfigs[configTab].cli && (
                    <div className="mcp-cli-alt">
                      <span className="mcp-cli-label">Or via CLI:</span>
                      <div className="mcp-config-block">
                        <div className="mcp-config-header">
                          <span>Terminal</span>
                          <button className="btn btn-small btn-secondary" onClick={() => copyToClipboard(clientConfigs[configTab].cli, "cli")}>
                            {copied === "cli" ? "Copied!" : "Copy"}
                          </button>
                        </div>
                        <pre className="mcp-config-code mcp-config-code-sm">{clientConfigs[configTab].cli}</pre>
                      </div>
                    </div>
                  )}
                </div>
              )}
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

      {openIncidentId !== null && (
        <IncidentReportModal
          incidentId={openIncidentId}
          onClose={() => setOpenIncidentId(null)}
          onUpdated={() => { loadIncidents(); loadIncidentCounts() }}
        />
      )}
    </div>
  )
}

export default McpPage
