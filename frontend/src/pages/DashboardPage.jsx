import { useState, useEffect, useCallback } from "react"
import { useAuth, useOrganization } from "@clerk/clerk-react"
import { getCameras, sendCameraCommand, forgetCamera, startRecording, stopRecording, getRecordingStatus } from "../services/api"
import CameraCard from "../components/CameraCard.jsx"

function DashboardPage() {
  const { getToken } = useAuth()
  const { organization } = useOrganization()
  const [cameras, setCameras] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [recordingStatus, setRecordingStatus] = useState({})

  const loadCameras = useCallback(async () => {
    if (!organization) return
    
    try {
      setLoading(true)
      setError(null)
      const token = await getToken()
      const data = await getCameras(() => Promise.resolve(token))
      console.log("[Dashboard] Received cameras data:", data)
      console.log("[Dashboard] Data type:", typeof data, "isArray:", Array.isArray(data))
      if (Array.isArray(data)) {
        console.log("[Dashboard] First camera (if any):", data[0])
      }
      const camerasMap = Array.isArray(data)
        ? data.reduce((acc, camera) => {
            console.log("[Dashboard] Processing camera:", camera)
            if (camera.camera_id) {
              acc[camera.camera_id] = camera
            } else {
              console.warn("[Dashboard] Camera missing camera_id:", camera)
            }
            return acc
          }, {})
        : data
      console.log("[Dashboard] Final camerasMap keys:", Object.keys(camerasMap))
      setCameras(camerasMap)
    } catch (err) {
      console.error("[Dashboard] Error loading cameras:", err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [organization, getToken])

  useEffect(() => {
    if (organization) {
      loadCameras()
      const interval = setInterval(loadCameras, 5000)
      return () => clearInterval(interval)
    }
  }, [organization, loadCameras])

  const handleCommand = async (cameraId, command) => {
    const token = await getToken()
    try {
      await sendCameraCommand(() => Promise.resolve(token), cameraId, command)
      setTimeout(loadCameras, 1000)
    } catch (err) {
      console.error("Command failed:", err)
    }
  }

  const handleForget = async (cameraId) => {
    if (window.confirm("Are you sure you want to forget this camera?")) {
      const token = await getToken()
      try {
        await forgetCamera(() => Promise.resolve(token), cameraId)
        loadCameras()
      } catch (err) {
        console.error("Forget failed:", err)
      }
    }
  }

  const handleStartRecording = async (cameraId) => {
    const token = await getToken()
    try {
      await startRecording(() => Promise.resolve(token), cameraId)
      const status = await getRecordingStatus(() => Promise.resolve(token), cameraId)
      setRecordingStatus(prev => ({ ...prev, [cameraId]: status }))
    } catch (err) {
      console.error("Start recording failed:", err)
    }
  }

  const handleStopRecording = async (cameraId) => {
    const token = await getToken()
    try {
      await stopRecording(() => Promise.resolve(token), cameraId)
      setRecordingStatus(prev => ({ ...prev, [cameraId]: { recording: false } }))
    } catch (err) {
      console.error("Stop recording failed:", err)
    }
  }

  const handleSnapshot = async (cameraId) => {
    const token = await getToken()
    try {
      await fetch(`/api/camera/${cameraId}/snapshot`, {
        headers: { 
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        }
      })
    } catch (err) {
      console.error("Snapshot failed:", err)
    }
  }

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
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Active Cameras</div>
          <div className="stat-value green">{stats.active}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Nodes</div>
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

      <div className="section-header">
        <h2 className="section-title">Camera Feeds</h2>
        <button onClick={loadCameras} className="btn btn-secondary">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
          Refresh
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
              onCommand={handleCommand}
              onForget={() => handleForget(cameraId)}
              onSnapshot={() => handleSnapshot(cameraId)}
              onStartRecording={() => handleStartRecording(cameraId)}
              onStopRecording={() => handleStopRecording(cameraId)}
              recordingStatus={recordingStatus[cameraId] || { recording: false }}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default DashboardPage