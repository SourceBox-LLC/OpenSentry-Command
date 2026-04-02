import { useEffect, useRef, useState } from "react"
import Hls from "hls.js"
import { useAuth } from "@clerk/clerk-react"

// Set to true to connect directly to CloudNode on localhost:8080
// Set to false to use backend proxy with authentication
const LOCAL_TEST_MODE = import.meta.env.VITE_LOCAL_HLS === "true"

function HlsPlayer({ cameraId, cameraName }) {
    const videoRef = useRef(null)
    const hlsRef = useRef(null)
    const { getToken } = useAuth()
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [isLive, setIsLive] = useState(false)

    useEffect(() => {
        const video = videoRef.current
        if (!video || !cameraId) {
            console.log("[HlsPlayer] No video ref or cameraId, skipping setup. cameraId:", cameraId)
            return
        }

        console.log("[HlsPlayer] Setting up HLS for camera:", cameraId)

        const API_URL = import.meta.env.VITE_API_URL || ""

        const setupHls = async () => {
            try {
                // In local test mode, connect directly to CloudNode
                // In production mode, use backend proxy with auth
                const playlistUrl = LOCAL_TEST_MODE
                    ? `http://localhost:8080/hls/${cameraId}/stream.m3u8`
                    : `${API_URL}/api/cameras/${cameraId}/stream.m3u8`

                console.log("[HlsPlayer] Playlist URL:", playlistUrl)
                console.log("[HlsPlayer] LOCAL_TEST_MODE:", LOCAL_TEST_MODE)
                console.log("[HlsPlayer] API_URL:", API_URL)

                if (Hls.isSupported()) {
                    const hls = new Hls({
                        xhrSetup: async (xhr) => {
                            // Only add auth header in production mode
                            if (!LOCAL_TEST_MODE) {
                                const token = await getToken()
                                if (token) {
                                    xhr.setRequestHeader("Authorization", `Bearer ${token}`)
                                }
                            }
                        },
                    })

                    hlsRef.current = hls

                    hls.loadSource(playlistUrl)
                    hls.attachMedia(video)

                    hls.on(Hls.Events.MANIFEST_PARSED, () => {
                        setLoading(false)
                        setIsLive(true)
                        video.play().catch(() => { })
                    })

                    hls.on(Hls.Events.ERROR, (event, data) => {
                        if (data.fatal) {
                            switch (data.type) {
                                case Hls.ErrorTypes.NETWORK_ERROR:
                                    setError("Network error - stream may not be active")
                                    setLoading(false)
                                    hls.startLoad()
                                    break
                                case Hls.ErrorTypes.MEDIA_ERROR:
                                    setError("Media error - attempting recovery")
                                    hls.recoverMediaError()
                                    break
                                default:
                                    setError("Stream error - cannot recover")
                                    hls.destroy()
                                    break
                            }
                        }
                    })
                } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
                    video.src = playlistUrl
                    video.addEventListener("loadedmetadata", () => {
                        setLoading(false)
                        setIsLive(true)
                        video.play().catch(() => { })
                    })
                } else {
                    setError("HLS is not supported in this browser")
                    setLoading(false)
                }
            } catch (err) {
                setError(err.message)
                setLoading(false)
            }
        }

        setupHls()

        return () => {
            if (hlsRef.current) {
                hlsRef.current.destroy()
                hlsRef.current = null
            }
        }
    }, [cameraId, getToken])

    if (error) {
        return (
            <div className="hls-player-error">
                <div className="error-icon">⚠️</div>
                <div className="error-text">{error}</div>
                <button 
                    className="btn btn-small"
                    onClick={() => {
                        setError(null)
                        setLoading(true)
                    }}
                >
                    Retry
                </button>
            </div>
        )
    }

    return (
        <div className="hls-player-container">
            <div className="hls-player-header">
                <h3>{cameraName || `Camera ${cameraId}`}</h3>
                {isLive && <span className="live-badge">LIVE</span>}
            </div>
            
            <div className="hls-player-video-wrapper">
                {loading && (
                    <div className="hls-player-loading">
                        <div className="loading-spinner"></div>
                        <p>Connecting to stream...</p>
                    </div>
                )}
                
                <video
                    ref={videoRef}
                    className="hls-player-video"
                    controls
                    playsInline
                    muted
                />
            </div>
            
            <div className="hls-player-controls">
                <button 
                    className="btn btn-small"
                    onClick={() => {
                        const video = videoRef.current
                        if (video) {
                            video.requestFullscreen?.() ||
                            video.webkitRequestFullscreen?.()
                        }
                    }}
                >
                    Fullscreen
                </button>
            </div>
        </div>
    )
}

export default HlsPlayer