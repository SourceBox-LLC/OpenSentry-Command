import { useState, useCallback, memo } from "react"
import { useAuth } from "@clerk/clerk-react"
import { requestSnapshot, setRecording } from "../services/api"
import { useToasts } from "../hooks/useToasts.jsx"
import HlsPlayer from "./HlsPlayer.jsx"

function CameraCard({
  cameraId,
  camera,
}) {
  const { getToken } = useAuth()
  const { showToast } = useToasts()
  const [snapshotLoading, setSnapshotLoading] = useState(false)
  const [snapshotMsg, setSnapshotMsg] = useState(null)
  const [recording, setRecordingState] = useState(false)
  const [recordLoading, setRecordLoading] = useState(false)

  const takeSnapshot = useCallback(async () => {
    setSnapshotLoading(true)
    setSnapshotMsg(null)
    try {
      await requestSnapshot(getToken, cameraId)
      setSnapshotMsg("Saved to node")
      showToast("Snapshot saved to node", "success")
    } catch (err) {
      setSnapshotMsg(err.message || "Snapshot failed")
      showToast(err.message || "Snapshot failed", "error")
    } finally {
      setSnapshotLoading(false)
      setTimeout(() => setSnapshotMsg(null), 3000)
    }
  }, [cameraId, getToken, showToast])

  const toggleRecording = useCallback(async () => {
    setRecordLoading(true)
    try {
      await setRecording(getToken, cameraId, !recording)
      setRecordingState(!recording)
      showToast(!recording ? "Recording started" : "Recording stopped", !recording ? "info" : "success")
    } catch (err) {
      console.error("Recording toggle failed:", err)
      showToast(err.message || "Recording toggle failed", "error")
    } finally {
      setRecordLoading(false)
    }
  }, [cameraId, getToken, recording, showToast])

  const isOffline = camera.status === "offline"

  const nodeTypeLabel = camera.node_type || "Camera"
  const nodeTypeIcon = "📹"

  const statusClass = camera.status === "online" ? "online" :
                      camera.status === "streaming" ? "streaming" :
                      camera.status === "recording" ? "recording" : "offline"

  const cardClasses = `camera-card ${isOffline ? "offline" : ""}`

  return (
    <div className={cardClasses}>
      <div className="camera-header">
        <div className="camera-info">
          <div className="camera-icon">{nodeTypeIcon}</div>
          <div className="camera-details">
            <h3>{camera.name || `Camera ${cameraId.slice(-4)}`}</h3>
            <span>{cameraId}</span>
            <span className="node-type">{nodeTypeLabel}</span>
          </div>
        </div>
        <div className={`status-badge ${statusClass}`}>
          <span className="dot"></span>
          <span className="status-text">{camera.status || "unknown"}</span>
        </div>
      </div>

      <div className="camera-feed-container">
        {isOffline ? (
          <div className="feed-loading error">
            <span className="status-icon">⚠️</span>
            <span>Camera Offline</span>
          </div>
        ) : (
          <HlsPlayer
            cameraId={cameraId}
            cameraName={camera.name || `Camera ${cameraId.slice(-4)}`}
            status={camera.status}
          />
        )}
      </div>

      <div className="camera-controls">
        <button
          className={`btn btn-record${recording ? " recording" : ""}`}
          onClick={toggleRecording}
          disabled={recordLoading}
          title={recording ? "Stop recording" : "Start recording on node"}
        >
          <span className={`record-dot${recording ? " active" : ""}`} />
          {recordLoading ? "..." : recording ? "Recording" : "Record"}
        </button>
        <button
          className="btn btn-snapshot"
          onClick={takeSnapshot}
          disabled={snapshotLoading}
          title="Take Snapshot (saved on camera node)"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="12" r="3.2"/>
            <path d="M9 2L7.17 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c0 1.1-.9-2-2V6c0-1.1-.9-2-2-2h-3.17L15 2H9zm3 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5z"/>
          </svg>
          {snapshotLoading ? "Capturing…" : snapshotMsg || "Snapshot"}
        </button>
      </div>

    </div>
  )
}

export default memo(CameraCard, (prevProps, nextProps) => {
  return (
    prevProps.cameraId === nextProps.cameraId &&
    prevProps.camera.status === nextProps.camera.status &&
    prevProps.camera.name === nextProps.camera.name
  )
})