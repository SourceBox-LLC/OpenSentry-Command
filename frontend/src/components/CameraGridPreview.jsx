import { useState, useEffect } from "react"

const CAMERA_NAMES = ["Front Door", "Backyard", "Garage", "Driveway"]

function CameraGridPreview() {
  const [cameras, setCameras] = useState(
    CAMERA_NAMES.map((name, i) => ({
      id: i,
      name,
      status: i === 0 ? "streaming" : i === 1 ? "streaming" : i === 2 ? "idle" : "streaming"
    }))
  )

  useEffect(() => {
    const interval = setInterval(() => {
      setCameras(prev => 
        prev.map(cam => ({
          ...cam,
          status: Math.random() > 0.7 
            ? (Math.random() > 0.5 ? "streaming" : "idle")
            : cam.status
        }))
      )
    }, 5000)

    return () => clearInterval(interval)
  }, [])

  return (
    <div className="dashboard-preview">
      <div className="preview-header">
        <div className="preview-dots">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <span className="preview-title">Command Center</span>
      </div>
      <div className="preview-content">
        <div className="preview-camera-grid">
          {cameras.map(camera => (
            <div key={camera.id} className="preview-camera-card">
              <div className="preview-camera-feed">
                <span className={`preview-camera-status ${camera.status}`}></span>
              </div>
              <div className="preview-camera-info">
                <span className={`preview-camera-status ${camera.status}`}></span>
                <span>{camera.name}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default CameraGridPreview