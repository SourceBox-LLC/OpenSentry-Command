import { useState, useEffect } from "react"
import { Link } from "react-router-dom"
import { useAuth, useOrganization } from "@clerk/clerk-react"
import { getStreamLogs, getStreamStats, getNodes, getPlanInfo } from "../services/api"
import { useToasts } from "../hooks/useToasts.jsx"
import UpgradeModal from "../components/UpgradeModal.jsx"

function AdminPage() {
  const { getToken } = useAuth()
  const { organization } = useOrganization()
  const { showToast } = useToasts()
  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState(null)
  const [nodes, setNodes] = useState([])
  const [loading, setLoading] = useState(true)
  const [statsLoading, setStatsLoading] = useState(true)
  const [planInfo, setPlanInfo] = useState(null)
  const [planLoading, setPlanLoading] = useState(true)

  const [filters, setFilters] = useState({
    camera_id: "",
    user_id: "",
    limit: 50,
    offset: 0,
  })
  const [total, setTotal] = useState(0)
  const [days, setDays] = useState(7)

  useEffect(() => {
    if (organization) {
      loadPlanInfo()
    }
  }, [organization])

  // Only load audit data once we know the plan allows it
  useEffect(() => {
    if (planInfo && planInfo.features?.includes("admin")) {
      loadNodes()
      loadLogs()
      loadStats()
    }
  }, [planInfo])

  const loadPlanInfo = async () => {
    try {
      setPlanLoading(true)
      const token = await getToken()
      const data = await getPlanInfo(() => Promise.resolve(token))
      setPlanInfo(data)
    } catch (err) {
      console.error("Failed to load plan info:", err)
    } finally {
      setPlanLoading(false)
    }
  }

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
            is available on the <strong>Pro</strong> and <strong>Business</strong> plans.
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
        <h2>Stream Access Logs</h2>
        <p className="section-description">
          View who has accessed your camera streams.
        </p>

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
    </div>
  )
}

export default AdminPage