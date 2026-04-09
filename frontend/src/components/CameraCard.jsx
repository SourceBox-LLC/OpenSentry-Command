import { useState, useEffect, useCallback, memo } from "react"
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
  const [showMotionHistory, setShowMotionHistory] = useState(false)
  const [showFaceHistory, setShowFaceHistory] = useState(false)
  const [showObjectHistory, setShowObjectHistory] = useState(false)
  const [detectionBadge, setDetectionBadge] = useState(null)
  const [snapshotLoading, setSnapshotLoading] = useState(false)
  const [snapshotMsg, setSnapshotMsg] = useState(null)
  const [recording, setRecordingState] = useState(false)
  const [recordLoading, setRecordLoading] = useState(false)

  useEffect(() => {
    if (camera.motion_active) {
      setDetectionBadge({ type: "motion", label: "MOTION" })
    } else if (camera.face_active) {
      setDetectionBadge({ type: "face", label: "FACE" })
    } else if (camera.objects_active) {
      setDetectionBadge({ type: "object", label: "OBJECTS" })
    } else {
      setDetectionBadge(null)
    }
  }, [camera.motion_active, camera.face_active, camera.objects_active])

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`
  }

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

  const nodeTypeLabel = camera.node_type || "USB Camera"
  const nodeTypeIcon = camera.node_type === "motion" ? "🎯" : 
                       camera.node_type === "face_camera" ? "👤" : 
                       camera.node_type === "object_camera" ? "🔍" : "📹"

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

      {camera.node_type === "motion" && (
        <div className="camera-motion-controls">
          <button 
            className="btn btn-motion-history"
            onClick={() => setShowMotionHistory(!showMotionHistory)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z"/>
            </svg>
            Motion History
          </button>
          <div className={`motion-history-panel ${showMotionHistory ? "" : "hidden"}`}>
            <div className="motion-events-mini">
              {camera.motion_events?.length > 0 ? (
                camera.motion_events.slice(-5).map((event, i) => (
                  <div key={`motion-${i}`} className="motion-event-mini">
                    <span className="event-icon">🎯</span>
                    <span className="event-time">
                      {new Date(event.timestamp * 1000).toLocaleTimeString()}
                    </span>
                    <span className="event-type">{event.event || "Motion"}</span>
                  </div>
                ))
              ) : (
                <p className="no-events">No recent motion events</p>
              )}
            </div>
          </div>
        </div>
      )}

      {camera.node_type === "face_camera" && (
        <div className="camera-face-controls">
          <button 
            className="btn btn-face-history"
            onClick={() => setShowFaceHistory(!showFaceHistory)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
            </svg>
            Face History
          </button>
          <div className={`face-history-panel ${showFaceHistory ? "" : "hidden"}`}>
            <div className="face-events-mini">
              {camera.face_events?.length > 0 ? (
                camera.face_events.slice(-5).map((event, i) => (
                  <div key={`face-${i}`} className="face-event-mini">
                    <span className="event-icon">📸</span>
                    <span className="event-time">
                      {new Date(event.timestamp * 1000).toLocaleTimeString()}
                    </span>
                    <span className="event-type">Face Detected</span>
                  </div>
                ))
              ) : (
                <p className="no-events">No recent face events</p>
              )}
            </div>
          </div>
        </div>
      )}

      {camera.node_type === "object_camera" && (
        <div className="camera-object-controls">
          <button 
            className="btn btn-object-history"
            onClick={() => setShowObjectHistory(!showObjectHistory)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4zM14 13h-3v3H9v-3H6v-2h3V8h2v3h3v2z"/>
            </svg>
            Object History
          </button>
          <div className={`object-history-panel ${showObjectHistory ? "" : "hidden"}`}>
            <div className="object-events-mini">
              {camera.object_events?.length > 0 ? (
                camera.object_events.slice(-5).map((event, i) => (
                  <div key={`object-${i}`} className="object-event-mini">
                    <span className="event-icon">🔍</span>
                    <span className="event-time">
                      {new Date(event.timestamp * 1000).toLocaleTimeString()}
                    </span>
                    <span className="event-type">
                      {event.objects?.join(", ") || "Objects"}
                    </span>
                  </div>
                ))
              ) : (
                <p className="no-events">No recent object detections</p>
              )}
            </div>
          </div>
        </div>
      )}
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