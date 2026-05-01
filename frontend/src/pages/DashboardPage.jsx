import { useState, useEffect, useCallback, useRef } from "react"
import { Link } from "react-router-dom"
import { useAuth, useOrganization } from "@clerk/clerk-react"
import { getCameras } from "../services/api"
import { useToasts } from "../hooks/useToasts.jsx"
import { usePlanInfo } from "../hooks/usePlanInfo.jsx"
import { useMotionAlerts } from "../hooks/useMotionAlerts.jsx"
import CameraCard from "../components/CameraCard.jsx"
import UpgradeModal from "../components/UpgradeModal.jsx"
import HeartbeatBanner from "../components/HeartbeatBanner.jsx"
import { AdminWelcomeHero, MemberWelcomeHero } from "../components/WelcomeHero.jsx"

function DashboardPage() {
  const { getToken } = useAuth()
  const { organization, membership } = useOrganization()
  const { showToast } = useToasts()
  const { planInfo } = usePlanInfo()
  const [cameras, setCameras] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showUpgrade, setShowUpgrade] = useState(false)
  const prevCamerasRef = useRef(null)
  const toastedOfflinesRef = useRef(new Set())

  const isAdmin = membership?.role === "org:admin"

  // Real-time motion detection notifications via SSE
  useMotionAlerts(cameras)

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

      // Only update state if data actually changed (shallow field comparison
      // instead of JSON.stringify — avoids blocking the main thread).
      const prev = prevCamerasRef.current
      let changed = !prev || Object.keys(camerasMap).length !== Object.keys(prev).length
      if (!changed) {
        for (const [id, cam] of Object.entries(camerasMap)) {
          const p = prev[id]
          if (!p || p.status !== cam.status || p.name !== cam.name || p.last_seen !== cam.last_seen) {
            changed = true
            break
          }
        }
      }
      if (changed) {
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

  useEffect(() => {
    if (!organization) return

    loadCameras()
    const interval = setInterval(loadCameras, 5000)
    return () => clearInterval(interval)
  }, [organization, loadCameras])


  // No manual refresh handler — the auto-refresh interval above
  // (loadCameras every 5s) keeps the dashboard live without user
  // action.  Manual button was removed once it became clear it was
  // a placebo: every Refresh click did the same fetch the background
  // poll already runs twice per 10s.

  const getStats = () => {
    const cameraList = Object.values(cameras)
    // "Active" = anything that's NOT in a known-down state.  Mirrors
    // the isDown logic used per-card in CameraCard.jsx so the stat
    // count and the per-card UI agree on what "down" means.
    // Includes streaming / online / recording / starting / restarting;
    // excludes offline / failed / error / plan-suspended.  Previous
    // version only counted streaming + online and undercounted any
    // camera in `recording` mode (continuous-24/7), which a 24/7
    // recording camera definitely is — that was a real bug.
    const active = cameraList.filter(c =>
      !(c.disabled_by_plan ||
        c.status === "offline" ||
        c.status === "failed" ||
        c.status === "error")
    ).length
    const total = cameraList.length
    const systemOk = total > 0
    return { active, total, systemOk }
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
      <HeartbeatBanner />

      {isAdmin && planInfo?.payment_past_due && (() => {
        // Grace countdown: backend returns grace_days_remaining + grace_expires_at.
        // When the timestamp parses cleanly we show the live number; otherwise
        // fall back to the ToS-guaranteed window (grace_window_days) so the
        // copy still reads correctly for older backends that haven't shipped
        // the countdown fields yet.
        const daysLeft = planInfo.grace_days_remaining
        const windowDays = planInfo.grace_window_days ?? 7
        let copy
        if (daysLeft === 0) {
          copy = (
            <>
              <strong>Grace period expired.</strong> Cameras beyond the free-tier
              limit are now suspended. Update your payment method to restore them.
            </>
          )
        } else if (typeof daysLeft === "number") {
          copy = (
            <>
              <strong>Payment past due — {daysLeft} day{daysLeft === 1 ? "" : "s"} left.</strong>
              {" "}After that, cameras beyond the free-tier limit will be suspended.
              Update your payment method now to avoid interruption.
            </>
          )
        } else {
          copy = (
            <>
              Your payment is past due. Cameras beyond your free-tier limit will be
              suspended after a {windowDays}-day grace period — update your payment method to
              keep streaming.
            </>
          )
        }
        return (
          <div
            className={`payment-past-due-banner${daysLeft === 0 ? " payment-past-due-expired" : ""}`}
            role="status"
            aria-live="polite"
          >
            <span>{copy}</span>
            <Link to="/pricing" className="btn btn-primary btn-small">
              Manage Billing
            </Link>
          </div>
        )
      })()}

      {planInfo && planInfo.features?.includes("admin") && (() => {
        // Pro Plus accepts both the new "pro_plus" slug and the transitional
        // "business" alias. Map both to the same CSS class so the badge
        // styling is consistent regardless of which slug the JWT carries.
        const isProPlus = planInfo.plan === "pro_plus" || planInfo.plan === "business"
        const planClass = isProPlus ? "pro-plus" : "pro"
        return (
        <div className={`pro-status-bar pro-status-${planClass}`}>
          <div className="pro-status-left">
            <span className="pro-status-badge">{isProPlus ? "PRO PLUS" : "PRO"}</span>
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
        )
      })()}

      {planInfo && typeof planInfo.usage?.viewer_hours_limit === "number" && (() => {
        // Viewer-hour usage panel — the real tier differentiator. Shown to
        // every org admin. Progress-bar colour ramps amber at 80% and red
        // at 100% so the signal is visually clear before we actually start
        // blocking segments.
        const used = planInfo.usage.viewer_hours_used || 0
        const limit = planInfo.usage.viewer_hours_limit
        const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0
        const state = pct >= 100 ? "full" : pct >= 80 ? "warn" : "ok"
        return (
          <div className={`usage-panel usage-${state}`} role="status" aria-live="polite">
            <div className="usage-panel-head">
              <div>
                <div className="usage-panel-title">Viewer hours this month</div>
                <div className="usage-panel-subtitle">
                  Live video playback counts against your monthly cap. Recordings on your node do not.
                </div>
              </div>
              <div className="usage-panel-count">
                <strong>{used.toFixed(1)}</strong>
                <span className="usage-panel-slash">/</span>
                <span>{limit}h</span>
              </div>
            </div>
            <div className="usage-panel-bar">
              <div className="usage-panel-fill" style={{ width: `${pct}%` }} />
            </div>
            {state === "warn" && (
              <div className="usage-panel-hint">
                Approaching your monthly cap — consider upgrading to keep streaming uninterrupted.
              </div>
            )}
            {state === "full" && (
              <div className="usage-panel-hint">
                Monthly cap reached. Live playback resumes on the 1st of next month, or upgrade for more viewing time.
              </div>
            )}
          </div>
        )
      })()}

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
        isAdmin
          ? <AdminWelcomeHero />
          : <MemberWelcomeHero orgName={organization?.name} />
      ) : (
        <div className="camera-grid">
          {Object.entries(cameras).map(([cameraId, camera]) => (
            <CameraCard
              key={cameraId}
              cameraId={cameraId}
              camera={camera}
              onRequestUpgrade={() => setShowUpgrade(true)}
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