import { useState, useEffect } from "react"
import { Link } from "react-router-dom"
import { useAuth, useOrganization } from "@clerk/clerk-react"
import { getStreamLogs, getStreamStats, getNodes, getMcpLogs, getMcpLogStats, downloadStreamLogsCsv, downloadMcpLogsCsv } from "../services/api"
import { useToasts } from "../hooks/useToasts.jsx"
import { usePlanInfo } from "../hooks/usePlanInfo.jsx"
import UpgradeModal from "../components/UpgradeModal.jsx"
import OrgAuditLogPanel from "../components/OrgAuditLogPanel.jsx"

function AdminPage() {
  const { getToken } = useAuth()
  const { organization } = useOrganization()
  const { showToast } = useToasts()
  const { planInfo, loading: planLoading } = usePlanInfo()
  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState(null)
  const [nodes, setNodes] = useState([])
  const [loading, setLoading] = useState(true)
  const [statsLoading, setStatsLoading] = useState(true)

  const [filters, setFilters] = useState({
    camera_id: "",
    user_id: "",
    limit: 50,
    offset: 0,
  })
  const [total, setTotal] = useState(0)
  const [days, setDays] = useState(7)

  // MCP activity state
  const [mcpLogs, setMcpLogs] = useState([])
  const [mcpStats, setMcpStats] = useState(null)
  const [mcpLoading, setMcpLoading] = useState(true)
  const [mcpStatsLoading, setMcpStatsLoading] = useState(true)
  const [mcpFilters, setMcpFilters] = useState({
    tool_name: "",
    key_name: "",
    status: "",
    limit: 50,
    offset: 0,
  })
  const [mcpTotal, setMcpTotal] = useState(0)
  const [mcpDays, setMcpDays] = useState(7)

  // Only load audit data once we know the plan allows it
  useEffect(() => {
    if (planInfo && planInfo.features?.includes("admin")) {
      loadNodes()
      loadLogs()
      loadStats()
      loadMcpLogs()
      loadMcpStats()
    }
  }, [planInfo])

  useEffect(() => {
    if (organization && planInfo?.features?.includes("admin")) {
      loadLogs()
    }
  }, [filters])

  const loadNodes = async () => {
    try {
      const token = await getToken()
      const data = await getNodes(() => Promise.resolve(token))
      setNodes(data)
    } catch (err) {
      console.error("Failed to load nodes:", err)
    }
  }

  const loadLogs = async () => {
    try {
      setLoading(true)
      const token = await getToken()

      const params = {}
      if (filters.camera_id) params.camera_id = filters.camera_id
      if (filters.user_id) params.user_id = filters.user_id
      params.limit = filters.limit
      params.offset = filters.offset

      const data = await getStreamLogs(() => Promise.resolve(token), params)
      setLogs(data.logs || [])
      setTotal(data.total || 0)
    } catch (err) {
      console.error("Failed to load audit logs:", err)
      showToast("Failed to load audit logs", "error")
    } finally {
      setLoading(false)
    }
  }

  const loadStats = async () => {
    try {
      setStatsLoading(true)
      const token = await getToken()
      const data = await getStreamStats(() => Promise.resolve(token), days)
      setStats(data)
    } catch (err) {
      console.error("Failed to load stats:", err)
      showToast("Failed to load statistics", "error")
    } finally {
      setStatsLoading(false)
    }
  }

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({
      ...prev,
      [key]: value,
      offset: 0,
    }))
  }

  const handlePageChange = (newOffset) => {
    setFilters(prev => ({
      ...prev,
      offset: newOffset,
    }))
  }

  const handleDaysChange = (newDays) => {
    setDays(newDays)
  }

  useEffect(() => {
    if (organization && planInfo?.features?.includes("admin")) {
      loadStats()
    }
  }, [days])

  // MCP activity loaders
  const loadMcpLogs = async () => {
    try {
      setMcpLoading(true)
      const token = await getToken()
      const data = await getMcpLogs(() => Promise.resolve(token), mcpFilters)
      setMcpLogs(data.logs || [])
      setMcpTotal(data.total || 0)
    } catch (err) {
      console.error("Failed to load MCP logs:", err)
    } finally {
      setMcpLoading(false)
    }
  }

  const loadMcpStats = async () => {
    try {
      setMcpStatsLoading(true)
      const token = await getToken()
      const data = await getMcpLogStats(() => Promise.resolve(token), mcpDays)
      setMcpStats(data)
    } catch (err) {
      console.error("Failed to load MCP stats:", err)
    } finally {
      setMcpStatsLoading(false)
    }
  }

  useEffect(() => {
    if (organization && planInfo?.features?.includes("admin")) {
      loadMcpLogs()
    }
  }, [mcpFilters])

  useEffect(() => {
    if (organization && planInfo?.features?.includes("admin")) {
      loadMcpStats()
    }
  }, [mcpDays])

  const handleMcpFilterChange = (key, value) => {
    setMcpFilters(prev => ({ ...prev, [key]: value, offset: 0 }))
  }

  const handleMcpPageChange = (newOffset) => {
    setMcpFilters(prev => ({ ...prev, offset: newOffset }))
  }

  // ── CSV export handlers ────────────────────────────────────────
  // Pass the active filters into the export so what the admin sees
  // on screen matches what they download.  Per-page (`limit`/`offset`)
  // is intentionally NOT forwarded — the CSV branch on the backend
  // ignores those and pulls a 50k-row window so an export is always
  // a meaningful audit slice, not just one screen-page worth.
  const [streamExporting, setStreamExporting] = useState(false)
  const [mcpExporting, setMcpExporting] = useState(false)

  const handleExportStreamCsv = async () => {
    setStreamExporting(true)
    try {
      const token = await getToken()
      const params = {}
      if (filters.camera_id) params.camera_id = filters.camera_id
      if (filters.user_id) params.user_id = filters.user_id
      await downloadStreamLogsCsv(() => Promise.resolve(token), params)
      showToast("Stream access log CSV downloaded.", "success")
    } catch (err) {
      console.error("Stream CSV export failed:", err)
      showToast(`Export failed: ${err.message || "unknown error"}`, "error")
    } finally {
      setStreamExporting(false)
    }
  }

  const handleExportMcpCsv = async () => {
    setMcpExporting(true)
    try {
      const token = await getToken()
      const params = {}
      if (mcpFilters.tool_name) params.tool_name = mcpFilters.tool_name
      if (mcpFilters.key_name) params.key_name = mcpFilters.key_name
      if (mcpFilters.status) params.status = mcpFilters.status
      await downloadMcpLogsCsv(() => Promise.resolve(token), params)
      showToast("MCP activity log CSV downloaded.", "success")
    } catch (err) {
      console.error("MCP CSV export failed:", err)
      showToast(`Export failed: ${err.message || "unknown error"}`, "error")
    } finally {
      setMcpExporting(false)
    }
  }

  if (!organization) {
    return (
      <div className="admin-container">
        <h1 className="page-title">Admin Dashboard</h1>
        <p className="text-muted">Please select an organization to view admin settings.</p>
      </div>
    )
  }

  if (planLoading) {
    return (
      <div className="admin-container">
        <h1 className="page-title">Admin Dashboard</h1>
        <div className="loading-spinner"></div>
      </div>
    )
  }

  if (!planInfo?.features?.includes("admin")) {
    return (
      <div className="admin-container">
        <div className="upgrade-prompt">
          <div className="upgrade-icon">🔒</div>
          <h2>Admin Dashboard</h2>
          <p>
            The Admin Dashboard with stream access logs and usage analytics
            is available on the <strong>Pro</strong> and <strong>Pro Plus</strong> plans.
          </p>
          <div className="upgrade-actions">
            <Link to="/pricing" className="btn btn-primary">
              Upgrade Your Plan
            </Link>
            <Link to="/dashboard" className="btn btn-secondary">
              Back to Dashboard
            </Link>
          </div>
        </div>
      </div>
    )
  }

  const pageCount = Math.ceil(total / filters.limit)
  const currentPage = Math.floor(filters.offset / filters.limit) + 1

  return (
    <div className="admin-container">
      <div className="admin-header">
        <h1>Admin Dashboard</h1>
        <p>View stream access logs and usage statistics for your organization.</p>
      </div>

      <div className="audit-section">
        <div className="audit-section-header">
          <div>
            <h2>Stream Access Logs</h2>
            <p className="section-description">
              View who has accessed your camera streams.
            </p>
          </div>
          {/*
            Export honours the active filters but ignores the
            per-page limit — backend pulls a 50k-row window so an
            audit export is always a meaningful slice, not just
            one screen-page.  See the docstring in the CSV
            branch of /api/audit/stream-logs for details.
          */}
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleExportStreamCsv}
            disabled={streamExporting}
            title="Download the current view (with filters applied) as a CSV file"
          >
            {streamExporting ? "Exporting…" : "Export CSV"}
          </button>
        </div>

        <div className="audit-filters">
          <div className="filter-group">
            <label>Camera</label>
            <select
              value={filters.camera_id}
              onChange={(e) => handleFilterChange("camera_id", e.target.value)}
            >
              <option value="">All Cameras</option>
              {nodes.map(node => (
                <option key={node.node_id} value={node.node_id}>
                  {node.name || `Node ${node.node_id}`}
                </option>
              ))}
            </select>
          </div>

          <div className="filter-group">
            <label>User Email</label>
            <input
              type="text"
              placeholder="Filter by email"
              value={filters.user_id}
              onChange={(e) => handleFilterChange("user_id", e.target.value)}
            />
          </div>

          <div className="filter-group">
            <label>Per Page</label>
            <select
              value={filters.limit}
              onChange={(e) => handleFilterChange("limit", parseInt(e.target.value))}
            >
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div className="loading-spinner"></div>
        ) : logs.length === 0 ? (
          <div className="audit-empty">
            <div className="audit-empty-icon">📊</div>
            <p>No stream access logs found.</p>
          </div>
        ) : (
          <>
            <div className="audit-table-wrapper">
              <table className="audit-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Camera</th>
                    <th>User</th>
                    <th>IP Address</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map(log => (
                    <tr key={log.id}>
                      <td className="timestamp">
                        {new Date(log.accessed_at).toLocaleString()}
                      </td>
                      <td>{log.camera_id}</td>
                      <td className="user-id">{log.user_email || log.user_id.substring(0, 8) + "..."}</td>
                      <td className="ip-address">{log.ip_address || "Unknown"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {pageCount > 1 && (
              <div className="audit-pagination">
                <button
                  onClick={() => handlePageChange(filters.offset - filters.limit)}
                  disabled={filters.offset === 0}
                >
                  Previous
                </button>
                {Array.from({ length: pageCount }, (_, i) => (
                  <button
                    key={i}
                    className={currentPage === i + 1 ? "active" : ""}
                    onClick={() => handlePageChange(i * filters.limit)}
                  >
                    {i + 1}
                  </button>
                ))}
                <button
                  onClick={() => handlePageChange(filters.offset + filters.limit)}
                  disabled={filters.offset + filters.limit >= total}
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </div>

      <div className="audit-section">
        <div className="stats-header">
          <h2>Statistics</h2>
          <select
            value={days}
            onChange={(e) => handleDaysChange(parseInt(e.target.value))}
          >
            <option value="1">Last 24 hours</option>
            <option value="7">Last 7 days</option>
            <option value="14">Last 14 days</option>
            <option value="30">Last 30 days</option>
          </select>
        </div>

        {statsLoading ? (
          <div className="loading-spinner"></div>
        ) : (
          <div className="stats-grid">
            <div className="stat-card">
              <h3>Total Accesses</h3>
              <div className="stat-value">{stats?.total_accesses || 0}</div>
            </div>

            <div className="stat-card">
              <h3>Top Cameras</h3>
              <ul className="stat-list">
                {stats?.by_camera?.slice(0, 5).map(item => (
                  <li key={item.camera_id}>
                    <span className="stat-name">{item.camera_id}</span>
                    <span className="stat-count">{item.count}</span>
                  </li>
                ))}
                {(!stats?.by_camera || stats.by_camera.length === 0) && (
                  <li><span className="stat-name">No data</span></li>
                )}
              </ul>
            </div>

            <div className="stat-card">
              <h3>Top Viewers</h3>
              <ul className="stat-list">
                {stats?.by_user?.slice(0, 5).map(item => (
                  <li key={item.user_id}>
                    <span className="stat-name">{item.user_email || item.user_id.substring(0, 12) + "..."}</span>
                    <span className="stat-count">{item.count}</span>
                  </li>
                ))}
                {(!stats?.by_user || stats.by_user.length === 0) && (
                  <li><span className="stat-name">No data</span></li>
                )}
              </ul>
            </div>

            <div className="stat-card">
              <h3>Daily Activity</h3>
              <ul className="stat-list">
                {stats?.by_day?.slice(0, 7).map(item => (
                  <li key={item.date}>
                    <span className="stat-name">{item.date}</span>
                    <span className="stat-count">{item.count}</span>
                  </li>
                ))}
                {(!stats?.by_day || stats.by_day.length === 0) && (
                  <li><span className="stat-name">No data</span></li>
                )}
              </ul>
            </div>
          </div>
        )}
      </div>

      {/*
        Organization Audit Log — write_audit() rows for member changes,
        MCP key gen, settings changes, danger-zone actions, etc.
        Self-contained component owns its state; mounted between the
        camera-stream audit (above) and the MCP-tool audit (below)
        so the three audit surfaces flow naturally as the operator
        scrolls.
      */}
      <OrgAuditLogPanel />

      {/* MCP Activity Logs */}
      <div className="audit-section">
        <div className="audit-section-header">
          <div>
            <h2>MCP Tool Activity</h2>
            <p className="section-description">
              AI tool call history — see what MCP clients have done with your cameras and data.
            </p>
          </div>
          {/* Same filter-aware CSV export as Stream Access Logs above.
              Useful for compliance ("show me every MCP call from
              ci_robot in March") and for diagnosing AI-agent
              regressions in a spreadsheet. */}
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleExportMcpCsv}
            disabled={mcpExporting}
            title="Download the current view (with filters applied) as a CSV file"
          >
            {mcpExporting ? "Exporting…" : "Export CSV"}
          </button>
        </div>

        <div className="audit-filters">
          <div className="filter-group">
            <label>Tool</label>
            <select
              value={mcpFilters.tool_name}
              onChange={(e) => handleMcpFilterChange("tool_name", e.target.value)}
            >
              <option value="">All Tools</option>
              <optgroup label="Key Management">
                <option value="key_created">key_created (MCP)</option>
                <option value="key_revoked">key_revoked (MCP)</option>
                <option value="node_key_created">node_key_created</option>
                <option value="node_key_rotated">node_key_rotated</option>
                <option value="node_deleted">node_deleted</option>
              </optgroup>
              <optgroup label="Camera Tools">
                <option value="view_camera">view_camera</option>
                <option value="watch_camera">watch_camera</option>
                <option value="list_cameras">list_cameras</option>
                <option value="get_camera">get_camera</option>
                <option value="get_stream_url">get_stream_url</option>
              </optgroup>
              <optgroup label="System Tools">
                <option value="list_nodes">list_nodes</option>
                <option value="get_node">get_node</option>
                <option value="list_camera_groups">list_camera_groups</option>
                <option value="get_stream_logs">get_stream_logs</option>
                <option value="get_stream_stats">get_stream_stats</option>
                <option value="get_system_status">get_system_status</option>
              </optgroup>
              <optgroup label="Recording Tools">
                <option value="get_camera_recording_policy">get_camera_recording_policy</option>
                <option value="set_camera_recording_policy">set_camera_recording_policy</option>
              </optgroup>
              <optgroup label="Incident Tools">
                <option value="list_incidents">list_incidents</option>
                <option value="get_incident">get_incident</option>
                <option value="get_incident_snapshot">get_incident_snapshot</option>
                <option value="get_incident_clip">get_incident_clip</option>
                <option value="create_incident">create_incident</option>
                <option value="add_observation">add_observation</option>
                <option value="attach_snapshot">attach_snapshot</option>
                <option value="attach_clip">attach_clip</option>
                <option value="update_incident">update_incident</option>
                <option value="finalize_incident">finalize_incident</option>
              </optgroup>
            </select>
          </div>

          <div className="filter-group">
            <label>API Key</label>
            <input
              type="text"
              placeholder="Filter by key name"
              value={mcpFilters.key_name}
              onChange={(e) => handleMcpFilterChange("key_name", e.target.value)}
            />
          </div>

          <div className="filter-group">
            <label>Status</label>
            <select
              value={mcpFilters.status}
              onChange={(e) => handleMcpFilterChange("status", e.target.value)}
            >
              <option value="">All</option>
              <option value="completed">Completed</option>
              <option value="error">Error</option>
            </select>
          </div>

          <div className="filter-group">
            <label>Per Page</label>
            <select
              value={mcpFilters.limit}
              onChange={(e) => handleMcpFilterChange("limit", parseInt(e.target.value))}
            >
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </div>
        </div>

        {mcpLoading ? (
          <div className="loading-spinner"></div>
        ) : mcpLogs.length === 0 ? (
          <div className="audit-empty">
            <div className="audit-empty-icon">🤖</div>
            <p>No MCP activity logs yet.</p>
          </div>
        ) : (
          <>
            <div className="audit-table-wrapper">
              <table className="audit-table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Tool</th>
                    <th>API Key</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {mcpLogs.map(log => {
                    const KEY_EVENT_LABELS = {
                      key_created: "MCP Key Created",
                      key_revoked: "MCP Key Revoked",
                      node_key_created: "Node Key Created",
                      node_key_rotated: "Node Key Rotated",
                      node_deleted: "Node Deleted",
                    }
                    const keyLabel = KEY_EVENT_LABELS[log.tool_name]
                    const isKeyEvent = !!keyLabel
                    const isDestructive = log.tool_name === "key_revoked" || log.tool_name === "node_deleted"
                    return (
                      <tr key={log.id} className={log.status === "error" ? "row-error" : isKeyEvent ? "row-admin" : ""}>
                        <td className="timestamp">
                          {new Date(log.timestamp).toLocaleString()}
                        </td>
                        <td>
                          {isKeyEvent ? (
                            <span className={`status-badge status-${isDestructive ? "key-revoked" : "key-created"}`}>
                              {keyLabel}
                            </span>
                          ) : (
                            <code>{log.tool_name}</code>
                          )}
                        </td>
                        <td>{log.key_name}</td>
                        <td>
                          <span className={`status-badge status-${log.status}`}>
                            {log.status}
                          </span>
                        </td>
                        <td>{log.duration_ms != null ? `${log.duration_ms}ms` : "—"}</td>
                        <td className="details-cell">
                          {log.error || log.args_summary || "—"}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {Math.ceil(mcpTotal / mcpFilters.limit) > 1 && (
              <div className="audit-pagination">
                <button
                  onClick={() => handleMcpPageChange(mcpFilters.offset - mcpFilters.limit)}
                  disabled={mcpFilters.offset === 0}
                >
                  Previous
                </button>
                <span className="page-info">
                  Page {Math.floor(mcpFilters.offset / mcpFilters.limit) + 1} of {Math.ceil(mcpTotal / mcpFilters.limit)}
                </span>
                <button
                  onClick={() => handleMcpPageChange(mcpFilters.offset + mcpFilters.limit)}
                  disabled={mcpFilters.offset + mcpFilters.limit >= mcpTotal}
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* MCP Statistics */}
      <div className="audit-section">
        <div className="stats-header">
          <h2>MCP Statistics</h2>
          <select
            value={mcpDays}
            onChange={(e) => setMcpDays(parseInt(e.target.value))}
          >
            <option value="1">Last 24 hours</option>
            <option value="7">Last 7 days</option>
            <option value="14">Last 14 days</option>
            <option value="30">Last 30 days</option>
          </select>
        </div>

        {mcpStatsLoading ? (
          <div className="loading-spinner"></div>
        ) : (
          <div className="stats-grid">
            <div className="stat-card">
              <h3>Total MCP Calls</h3>
              <div className="stat-value">{mcpStats?.total_calls || 0}</div>
              {mcpStats?.total_errors > 0 && (
                <div className="stat-sub error">{mcpStats.total_errors} errors</div>
              )}
            </div>

            <div className="stat-card">
              <h3>Top Tools</h3>
              <ul className="stat-list">
                {mcpStats?.by_tool?.slice(0, 5).map(item => (
                  <li key={item.tool_name}>
                    <span className="stat-name"><code>{item.tool_name}</code></span>
                    <span className="stat-count">{item.count}</span>
                  </li>
                ))}
                {(!mcpStats?.by_tool || mcpStats.by_tool.length === 0) && (
                  <li><span className="stat-name">No data</span></li>
                )}
              </ul>
            </div>

            <div className="stat-card">
              <h3>By API Key</h3>
              <ul className="stat-list">
                {mcpStats?.by_key?.slice(0, 5).map(item => (
                  <li key={item.key_name}>
                    <span className="stat-name">{item.key_name}</span>
                    <span className="stat-count">{item.count}</span>
                  </li>
                ))}
                {(!mcpStats?.by_key || mcpStats.by_key.length === 0) && (
                  <li><span className="stat-name">No data</span></li>
                )}
              </ul>
            </div>

            <div className="stat-card">
              <h3>MCP Daily Activity</h3>
              <ul className="stat-list">
                {mcpStats?.by_day?.slice(0, 7).map(item => (
                  <li key={item.date}>
                    <span className="stat-name">{item.date}</span>
                    <span className="stat-count">{item.count}</span>
                  </li>
                ))}
                {(!mcpStats?.by_day || mcpStats.by_day.length === 0) && (
                  <li><span className="stat-name">No data</span></li>
                )}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default AdminPage