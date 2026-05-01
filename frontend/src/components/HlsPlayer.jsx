import { useEffect, useRef, useState } from "react"
import { useSharedToken } from "../hooks/useSharedToken.jsx"

// hls.js is ~500 KB / ~155 KB gzipped. Static import would bloat the main
// bundle on every route — including landing/pricing/security/docs which
// never play video. Dynamic import below keeps it out until a HlsPlayer
// actually mounts. The first video tile takes one extra round-trip to
// fetch the chunk (cached thereafter); every other route gets a faster
// first paint.

// Set to true to connect directly to CloudNode on localhost:8080
// Set to false to use backend proxy with authentication
const LOCAL_TEST_MODE = import.meta.env.VITE_LOCAL_HLS === "true"

function HlsPlayer({ cameraId, cameraName }) {
    const videoRef = useRef(null)
    const hlsRef = useRef(null)
    const stallRef = useRef(null)
    const { getCurrentToken, refreshNow, ready } = useSharedToken()
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [isLive, setIsLive] = useState(false)

    useEffect(() => {
        const video = videoRef.current
        if (!video || !cameraId) {
                return
        }

        // Wait for the shared Clerk token before building the hls.js
        // instance.  Mounting earlier means the first playlist/segment
        // XHR fires with a null Authorization header → 401 → fatal
        // NETWORK_ERROR → forced recovery.  Usually survives but leaves
        // the player stuck on "Connecting…" for a beat and spams 401s
        // in the backend log on every page load.
        if (!LOCAL_TEST_MODE && !ready) {
            return
        }

        const API_URL = import.meta.env.VITE_API_URL || ""
        const ownOrigin = API_URL || window.location.origin

        // Cancellation flag for the async chunk load below — if the
        // component unmounts (or cameraId changes) while the dynamic
        // import is still in flight, we must NOT proceed to instantiate
        // an Hls that nobody will clean up. The cleanup function below
        // flips this to true.
        let cancelled = false

        const setupHls = async () => {
            try {
                // Lazy-load hls.js. Vite splits it into its own chunk
                // (see comment at top of file). After the first call in
                // a session the browser cache serves the chunk
                // instantly; the cost is one round-trip on the first
                // video the user opens.
                const { default: Hls } = await import("hls.js")
                if (cancelled) return

                const playlistUrl = LOCAL_TEST_MODE
                    ? `http://localhost:8080/hls/${cameraId}/stream.m3u8`
                    : `${API_URL}/api/cameras/${cameraId}/stream.m3u8`

                if (Hls.isSupported()) {
                    const hls = new Hls({
                        // Don't auto-start loading — we call startLoad(-1)
                        // in MANIFEST_PARSED to ensure playback always begins
                        // from the live edge, not from a stale buffer position.
                        autoStartLoad: false,

                        xhrSetup: (xhr, url) => {
                            const token = LOCAL_TEST_MODE ? null : getCurrentToken()
                            // hls.js may pass relative URLs (e.g. "segment/segment_00042.ts")
                            // or absolute URLs (e.g. "https://...stream.m3u8").  Always attach
                            // the token for our own API endpoints; skip third-party origins.
                            if (token && (url.startsWith(ownOrigin) || url.startsWith("/"))) {
                                xhr.setRequestHeader("Authorization", `Bearer ${token}`)
                                // Prevent browser from serving cached playlist/segment
                                xhr.setRequestHeader("Cache-Control", "no-cache")
                            }
                        },

                        // ── Latency tuning ────────────────────────────────────
                        // Pipeline latency (FFmpeg → push → backend cache → browser) is ~2-3s.
                        // With 1s segments, 4 segments behind live = enough
                        // headroom to absorb upload jitter without stalling.
                        liveSyncDurationCount: 4,        // stay 4 segments (4s) behind live
                        liveMaxLatencyDurationCount: 8,  // if >8 segs (8s) behind, jump to live
                        liveDurationInfinity: true,      // never treat the stream as ended
                        liveBackBufferLength: 10,        // keep 10s of back buffer in live mode

                        // Forward buffer: generous to ride out upload jitter
                        maxBufferLength: 10,
                        maxMaxBufferLength: 20,
                        maxBufferSize: 20 * 1024 * 1024, // 20 MB

                        // Back buffer: liveBackBufferLength (above) governs
                        // this in live mode.  backBufferLength is the
                        // VOD-mode equivalent — kept in sync so switching
                        // a live stream to a DVR-style replay wouldn't
                        // silently change retention.
                        backBufferLength: 10,

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
                    stallRef.current = stallCheck

                    hls.on(Hls.Events.ERROR, (event, data) => {
                        if (data.fatal) {
                            switch (data.type) {
                                case Hls.ErrorTypes.NETWORK_ERROR:
                                    // Network errors are often caused by an expired
                                    // auth token (401). Refresh the shared token
                                    // immediately before retrying.
                                    console.warn("[HlsPlayer] Network error, refreshing token and retrying:", data.details)
                                    refreshNow().then(() => {
                                        hls.startLoad()
                                    })
                                    break
                                case Hls.ErrorTypes.MEDIA_ERROR:
                                    console.warn("[HlsPlayer] Media error, recovering:", data.details)
                                    hls.recoverMediaError()
                                    break
                                default:
                                    setError(`Fatal error: ${data.type}`)
                                    if (stallRef.current) {
                                        clearInterval(stallRef.current)
                                        stallRef.current = null
                                    }
                                    hls.destroy()
                                    hlsRef.current = null
                                    break
                            }
                        }
                    })
                } else {
                    setError("Your browser does not support HLS streaming. Please use a modern browser (Chrome, Firefox, Edge, or Safari 13+).")
                    setLoading(false)
                }
            } catch (err) {
                setError(err.message)
                setLoading(false)
            }
        }

        setupHls()

        return () => {
            // Block the late branch in setupHls (post-await) from running
            // its setup if the dynamic import hasn't resolved yet.
            cancelled = true
            if (stallRef.current) {
                clearInterval(stallRef.current)
                stallRef.current = null
            }
            if (hlsRef.current) {
                hlsRef.current.destroy()
                hlsRef.current = null
            }
        }
    }, [cameraId, getCurrentToken, ready])

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
                        {/*
                            Custom loading state — branded camera-pulse SVG instead
                            of the generic .loading-spinner (which is shared with
                            auth pages and empty states).  Keeps the connecting UI
                            on-brand and matches the SourceBox green accent.
                        */}
                        <svg
                            className="camera-pulse"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.75"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            aria-hidden="true"
                        >
                            <path d="M23 7l-7 5 7 5V7z" />
                            <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                        </svg>
                        <p>Connecting to stream...</p>
                    </div>
                )}

                {/*
                    No `controls` attribute on purpose.  The native HTML5 control
                    bar (play/pause, scrubber, time, mute, fullscreen) renders on
                    top of the video and is visible during the connect window AND
                    during normal playback — pure visual noise for our use case:
                      - every player is `muted` (line below) so volume is moot
                      - live streams aren't seekable
                      - autoplay starts on MANIFEST_PARSED so play/pause is moot
                      - the dedicated Fullscreen button below replaces the native
                        fullscreen icon
                    Removing `controls` cleans up both the loading state and the
                    steady-state playback view.  Right-click "Save video as" goes
                    away too, which is a nice security adjacent.
                */}
                <video
                    ref={videoRef}
                    className="hls-player-video"
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