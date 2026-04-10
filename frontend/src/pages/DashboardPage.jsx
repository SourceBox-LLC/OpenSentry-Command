import { useState, useEffect, useCallback, useRef } from "react"
import { Link } from "react-router-dom"
import { useAuth, useOrganization } from "@clerk/clerk-react"
import { getCameras, getPlanInfo } from "../services/api"
import { useToasts } from "../hooks/useToasts.jsx"
import CameraCard from "../components/CameraCard.jsx"
import UpgradeModal from "../components/UpgradeModal.jsx"

function DashboardPage() {
  const { getToken } = useAuth()
  const { organization, membership } = useOrganization()
  const { showToast } = useToasts()
  const [cameras, setCameras] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [planInfo, setPlanInfo] = useState(null)
  const [showUpgrade, setShowUpgrade] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const prevCamerasRef = useRef(null)
  const toastedOfflinesRef = useRef(new Set())

  const isAdmin = membership?.role === "org:admin"

  const loadCameras = useCallback(async () => {
    if (!organization) return
    
    try {
      setError(null)
      const token = await getToken()
      const data = await getCameras(() => Promise.resolve(token))
      
      const camerasMap = Array.isArray(data)
        ? data.reduce((acc, camera) => {
            if (camera.camera_id) {
              acc[camera.camera_id] = camera
            }
            return acc
          }, {})
        : data
      
      // Detect cameras that just went offline
      if (prevCamerasRef.current) {
        const newlyOffline = []
        for (const [id, cam] of Object.entries(camerasMap)) {
          const prev = prevCamerasRef.current[id]
          if (prev && prev.status !== "offline" && cam.status === "offline") {
            newlyOffline.push(cam.name || id)
          }
        }
        if (newlyOffline.length > 0) {
          // Only toast each camera once per offline event
          const fresh = newlyOffline.filter(n => !toastedOfflinesRef.current.has(n))
          if (fresh.length > 0) {
            fresh.forEach(n => toastedOfflinesRef.current.add(n))
            const msg = fresh.length === 1
              ? `Camera "${fresh[0]}" went offline`
              : `${fresh.length} cameras went offline`
            showToast(msg, "warning")
          }
        }
        // Clear from toasted set when cameras come back online
        for (const [id, cam] of Object.entries(camerasMap)) {
          if (cam.status !== "offline") {
            const name = cam.name || id
            if (toastedOfflinesRef.current.has(name)) {
              toastedOfflinesRef.current.delete(name)
              showToast(`Camera "${name}" is back online`, "success")
            }
          }
        }
      }

      // Only update state if data actually changed
      const prevKeys = prevCamerasRef.current ? Object.keys(prevCamerasRef.current).join(',') : ''
      const newKeys = Object.keys(camerasMap).join(',')

      if (prevKeys !== newKeys ||
          JSON.stringify(prevCamerasRef.current) !== JSON.stringify(camerasMap)) {
        prevCamerasRef.current = camerasMap
        setCameras(camerasMap)
      }
    } catch (err) {
      console.error("[Dashboard] Error loading cameras:", err)
      // Only toast on first error, not every poll cycle
      if (!error) showToast("Failed to load cameras", "error")
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [organization, getToken])

  const loadPlanInfo = useCallback(async () => {
    if (!organization) return
    try {
      const token = await getToken()
      const data = await getPlanInfo(() => Promise.resolve(token))
      setPlanInfo(data)
    } catch (err) {
      console.error("[Dashboard] Error loading plan info:", err)
    }
  }, [organization, getToken])

  useEffect(() => {
    if (!organization) return

    loadCameras()
    loadPlanInfo()
    const interval = setInterval(loadCameras, 5000)
    // Refresh plan info less frequently (every 60s)
    const planInterval = setInterval(loadPlanInfo, 60000)
    return () => {
      clearInterval(interval)
      clearInterval(planInterval)
    }
  }, [organization, loadCameras, loadPlanInfo])


  const handleRefresh = useCallback(async () => {
    setRefreshing(true)
    prevCamerasRef.current = null // force state update
    await loadCameras()
    await loadPlanInfo()
    setRefreshing(false)
  }, [loadCameras, loadPlanInfo])

  const getStats = () => {
    const cameraList = Object.values(cameras)
    const active = cameraList.filter(c => c.status === "streaming" || c.status === "online").length
    const total = cameraList.length
    const streaming = cameraList.filter(c => c.status === "streaming").length
    const systemOk = Object.keys(cameras).length > 0
    return { active, total, streaming, systemOk }
  }

  if (!organization) {
    return (
      <div className="home-container">
        <div className="no-org-container">
          <h1 className="hero-title">No Organization Selected</h1>
          <p className="no-org-text">
            Create or join an organization to start managing your security cameras.
          </p>
        </div>
      </div>
    )
  }

  const stats = getStats()

  return (
    <div className="dashboard-container">
      {isAdmin && planInfo?.payment_past_due && (
        <div className="payment-past-due-banner">
          <span>Your payment is past due. Please update your billing information to avoid service interruption.</span>
          <Link to="/settings">Update Billing</Link>
        </div>
      )}

      {planInfo && planInfo.features?.includes("admin") && (
        <div className={`pro-status-bar pro-status-${planInfo.plan}`}>
          <div className="pro-status-left">
            <span className="pro-status-badge">{planInfo.plan === "business" ? "BUSINESS" : "PRO"}</span>
            <span className="pro-status-text">
              {planInfo.usage.cameras} / {planInfo.limits.max_cameras >= 999 ? "\u221E" : planInfo.limits.max_cameras} cameras
              {" \u00B7 "}
              {planInfo.usage.nodes} / {planInfo.limits.max_nodes >= 999 ? "\u221E" : planInfo.limits.max_nodes} nodes
              {" \u00B7 "}
              MCP + Admin + Analytics
            </span>
          </div>
          <Link to="/settings" className="pro-status-link">Manage Plan</Link>
        </div>
      )}

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Active Cameras</div>
          <div className="stat-value green">{stats.active}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Cameras</div>
          <div className="stat-value blue">{stats.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Streaming</div>
          <div className="stat-value green">{stats.streaming}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">System Status</div>
          <div className={`stat-value ${stats.systemOk ? "green" : "amber"}`}>
            {stats.systemOk ? "Ready" : "Offline"}
          </div>
        </div>
      </div>

      {isAdmin && planInfo && planInfo.usage.cameras >= planInfo.limits.max_cameras && (
        <div className="plan-limit-banner">
          <span className="plan-limit-text">
            You've reached your camera limit ({planInfo.limits.max_cameras} on the {planInfo.plan_name} plan).
            New cameras won't be added until you upgrade.
          </span>
          <button className="btn btn-primary btn-small" onClick={() => setShowUpgrade(true)}>
            Upgrade
          </button>
        </div>
      )}

      {isAdmin && planInfo && planInfo.usage.cameras >= Math.floor(planInfo.limits.max_cameras * 0.8) && planInfo.usage.cameras < planInfo.limits.max_cameras && (
        <div className="plan-limit-banner plan-limit-warning">
          <span className="plan-limit-text">
            You're using {planInfo.usage.cameras} of {planInfo.limits.max_cameras} cameras on the {planInfo.plan_name} plan.
          </span>
          <button className="btn btn-secondary btn-small" onClick={() => setShowUpgrade(true)}>
            View Plans
          </button>
        </div>
      )}

      <div className="section-header">
        <h2 className="section-title">Camera Feeds</h2>
        <button onClick={handleRefresh} className="btn btn-secondary" disabled={refreshing}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            style={refreshing ? { animation: 'spin 0.8s linear infinite' } : {}}>
            <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
          {refreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {loading ? (
        <div className="empty-state">
          <div className="loading-spinner"></div>
          <p>Loading cameras...</p>
        </div>
      ) : error ? (
        <div className="empty-state">
          <div className="empty-icon">⚠️</div>
          <h3>Error Loading Cameras</h3>
          <p>{error}</p>
          <button onClick={loadCameras} className="btn btn-primary">
            Retry
          </button>
        </div>
      ) : Object.keys(cameras).length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📹</div>
          <h3>No Camera Nodes Found</h3>
          <p>Go to Settings to add and configure your OpenSentry camera nodes.</p>
        </div>
      ) : (
        <div className="camera-grid">
          {Object.entries(cameras).map(([cameraId, camera]) => (
            <CameraCard
              key={cameraId}
              cameraId={cameraId}
              camera={camera}
            />
          ))}
        </div>
      )}

      <UpgradeModal
        isOpen={showUpgrade}
        onClose={() => setShowUpgrade(false)}
        feature="cameras"
        currentPlan={planInfo?.plan}
      />
    </div>
  )
}

export default DashboardPage