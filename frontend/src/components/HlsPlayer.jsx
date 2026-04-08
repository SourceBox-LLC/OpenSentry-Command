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
                return
        }

        const API_URL = import.meta.env.VITE_API_URL || ""
        const ownOrigin = API_URL || window.location.origin

        const setupHls = async () => {
            try {
                const playlistUrl = LOCAL_TEST_MODE
                    ? `http://localhost:8080/hls/${cameraId}/stream.m3u8`
                    : `${API_URL}/api/cameras/${cameraId}/stream.m3u8`

                // Pre-fetch the auth token BEFORE creating hls.js.
                // xhrSetup is called synchronously — an async callback
                // would return a Promise that hls.js never awaits, so
                // the request would fire without the Authorization header.
                let authToken = null
                if (!LOCAL_TEST_MODE) {
                    authToken = await getToken()
                }

                if (Hls.isSupported()) {
                    const hls = new Hls({
                        xhrSetup: (xhr, url) => {
                            // Only send auth header to our own backend.
                            // Presigned Tigris URLs already carry auth in the query
                            // string — sending an Authorization header to Tigris
                            // triggers a CORS preflight that Tigris rejects.
                            if (authToken && url.startsWith(ownOrigin)) {
                                xhr.setRequestHeader("Authorization", `Bearer ${authToken}`)
                            }
                        },

                        // ── Latency tuning (1-second segments) ────────────────
                        // Pipeline latency (FFmpeg → upload → Tigris → browser) is ~2-3s.
                        // With 1s segments, 3 segments = 3s behind live — enough
                        // headroom to absorb upload jitter without stalling.
                        liveSyncDurationCount: 4,        // stay 4 segments (4s) behind live
                        liveMaxLatencyDurationCount: 8,  // if >8 segs (8s) behind, jump to live
                        liveDurationInfinity: true,      // never treat the stream as ended
                        liveBackBufferLength: 10,        // keep 10s of back buffer in live mode

                        // Forward buffer: generous to ride out upload jitter
                        maxBufferLength: 10,
                        maxMaxBufferLength: 20,
                        maxBufferSize: 20 * 1024 * 1024, // 20 MB

                        // Back buffer: moderate trim to limit memory on long streams
                        backBufferLength: 15,

                        // Playlist reload — poll aggressively for new segments.
                        manifestLoadingMaxRetry: 15,
                        manifestLoadingRetryDelay: 400,
                        manifestLoadingTimeOut: 10000,
                        levelLoadingMaxRetry: 15,
                        levelLoadingRetryDelay: 400,
                        levelLoadingTimeOut: 10000,
                        fragLoadingMaxRetry: 15,
                        fragLoadingRetryDelay: 400,
                        fragLoadingTimeOut: 10000,

                        enableWorker: true,
                    })

                    hlsRef.current = hls

                    // Refresh the auth token every 30 seconds so it never
                    // reaches Clerk's 60s expiry. If a refresh fails, the
                    // next attempt is only 30s away (not 50s).
                    const tokenRefreshInterval = setInterval(async () => {
                        try {
                            authToken = await getToken()
                        } catch (e) {
                            console.warn("[HlsPlayer] Token refresh failed:", e)
                        }
                    }, 30000)

                    // Store interval ID for cleanup
                    hls._tokenRefreshInterval = tokenRefreshInterval

                    // Helper: refresh token immediately (called on auth failures)
                    const refreshTokenNow = async () => {
                        try {
                            authToken = await getToken()
                        } catch (e) {
                            console.warn("[HlsPlayer] Urgent token refresh failed:", e)
                        }
                    }

                    hls.loadSource(playlistUrl)
                    hls.attachMedia(video)

                    hls.on(Hls.Events.MANIFEST_PARSED, () => {
                        setLoading(false)
                        setIsLive(true)
                        // Start playback from the live edge, not from the
                        // beginning of the buffer.
                        hls.startLoad(-1)
                        video.play().catch(() => { })
                    })

                    // If the player falls too far behind live, snap back.
                    hls.on(Hls.Events.LEVEL_UPDATED, (_, data) => {
                        if (data.live && video && !video.paused) {
                            const liveEdge = hls.liveSyncPosition
                            if (liveEdge && video.currentTime < liveEdge - 6) {
                                console.warn("[HlsPlayer] Fell behind live edge, snapping forward")
                                video.currentTime = liveEdge
                            }
                        }
                    })

                    // Stall recovery: if the player hasn't advanced in 2 seconds
                    // while playing, it's stuck. Jump to live edge to break out
                    // of it — this is what a page refresh does, but automatically.
                    let lastTime = 0
                    let stallCount = 0
                    const stallCheck = setInterval(() => {
                        if (!video || video.paused) return

                        if (Math.abs(video.currentTime - lastTime) < 0.1) {
                            stallCount++
                            if (stallCount >= 2) {
                                // Stalled for 2+ seconds — jump to live
                                const liveEdge = hls.liveSyncPosition
                                if (liveEdge && liveEdge > video.currentTime + 1) {
                                    console.warn(`[HlsPlayer] Stall detected (${stallCount}s), jumping to live edge`)
                                    video.currentTime = liveEdge
                                    hls.startLoad(-1)
                                    setLoading(false)
                                }
                                stallCount = 0
                            }
                        } else {
                            stallCount = 0
                            setLoading(false)
                        }
                        lastTime = video.currentTime
                    }, 1000)
                    hls._stallCheck = stallCheck

                    hls.on(Hls.Events.ERROR, (event, data) => {
                        if (data.fatal) {
                            switch (data.type) {
                                case Hls.ErrorTypes.NETWORK_ERROR:
                                    // Network errors are often caused by an expired
                                    // auth token (401). Refresh the token immediately
                                    // before retrying, so the next request uses a
                                    // fresh token instead of the stale one.
                                    console.warn("[HlsPlayer] Network error, refreshing token and retrying:", data.details)
                                    refreshTokenNow().then(() => {
                                        hls.startLoad()
                                    })
                                    break
                                case Hls.ErrorTypes.MEDIA_ERROR:
                                    console.warn("[HlsPlayer] Media error, recovering:", data.details)
                                    hls.recoverMediaError()
                                    break
                                default:
                                    setError(`Fatal error: ${data.type}`)
                                    hls.destroy()
                                    break
                            }
                        }
                    })
                } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
                    video.src = playlistUrl
                    const onLoadedMetadata = () => {
                        setLoading(false)
                        setIsLive(true)
                        video.play().catch(() => { })
                    }
                    video.addEventListener("loadedmetadata", onLoadedMetadata)
                    // Store for cleanup
                    video._hlsMetadataHandler = onLoadedMetadata
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
                if (hlsRef.current._tokenRefreshInterval) {
                    clearInterval(hlsRef.current._tokenRefreshInterval)
                }
                if (hlsRef.current._stallCheck) {
                    clearInterval(hlsRef.current._stallCheck)
                }
                hlsRef.current.destroy()
                hlsRef.current = null
            }
            // Clean up native HLS event listener (Safari fallback)
            const vid = videoRef.current
            if (vid && vid._hlsMetadataHandler) {
                vid.removeEventListener("loadedmetadata", vid._hlsMetadataHandler)
                delete vid._hlsMetadataHandler
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