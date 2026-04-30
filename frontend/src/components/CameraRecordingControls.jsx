import { useState } from "react"
import { useAuth } from "@clerk/clerk-react"
import { updateCameraRecordingPolicy } from "../services/api"

/**
 * Per-camera recording-policy controls (v0.1.43+).
 *
 * Shown inside each Camera Nodes card on Settings, one row per
 * camera under the storage bar.  Replaces the previous org-wide
 * Settings → Recording section, which never actually drove
 * recording (its toggles persisted to a Setting row but no consumer
 * read them).  Per-camera here is the granularity that matches how
 * recording state is keyed at runtime in CloudNode and lets
 * operators record some cameras 24/7 while leaving others off for
 * privacy / storage reasons.
 *
 * Props:
 *   - camera: the camera object (must include `recording_policy`)
 *   - onUpdated: optional callback invoked with the new policy after
 *     a successful PATCH; parent uses this to refresh local state
 *     so the toggle is immediately reflected in the card.
 *
 * Optimistic UI: the toggle flips immediately; if the PATCH fails
 * we roll back to the previous state and surface a toast.  Avoids
 * the lag where a user clicks twice because nothing visually
 * changed for half a second.
 */
function CameraRecordingControls({ camera, onUpdated }) {
  const { getToken } = useAuth()
  const policy = camera.recording_policy || {
    continuous_24_7: false,
    scheduled_recording: false,
    scheduled_start: null,
    scheduled_end: null,
  }

  // Local mirror of policy for optimistic updates.  Initialized from
  // props but diverges briefly during a PATCH-in-flight.
  const [local, setLocal] = useState(policy)
  const [saving, setSaving] = useState(false)

  const persist = async (next) => {
    const previous = local
    setLocal(next)
    setSaving(true)
    try {
      const token = await getToken()
      const resp = await updateCameraRecordingPolicy(
        () => Promise.resolve(token),
        camera.camera_id,
        next,
      )
      // Server-canonical state may differ slightly (e.g., null
      // normalization) — sync to whatever the server actually saved.
      if (resp?.recording_policy) {
        setLocal(resp.recording_policy)
        if (onUpdated) onUpdated(resp.recording_policy)
      } else if (onUpdated) {
        onUpdated(next)
      }
    } catch (err) {
      // Roll back on failure.
      setLocal(previous)
      console.error("Recording policy update failed:", err)
    } finally {
      setSaving(false)
    }
  }

  const onToggleContinuous = () => {
    persist({ ...local, continuous_24_7: !local.continuous_24_7 })
  }

  const onToggleScheduled = () => {
    // Default the window to a reasonable 8am–5pm if scheduled is being
    // turned on for the first time and no window has been set.
    const next = {
      ...local,
      scheduled_recording: !local.scheduled_recording,
    }
    if (!local.scheduled_recording) {
      next.scheduled_start = local.scheduled_start || "08:00"
      next.scheduled_end = local.scheduled_end || "17:00"
    }
    persist(next)
  }

  const onChangeTime = (field, value) => {
    persist({ ...local, [field]: value })
  }

  return (
    <div
      className="camera-recording-controls"
      style={{
        marginTop: "0.5rem",
        padding: "0.6rem 0.75rem",
        background: "var(--bg-primary, #0a0a0a)",
        border: "1px solid var(--border, #2a2a2a)",
        borderRadius: "6px",
        opacity: saving ? 0.7 : 1,
        transition: "opacity 0.2s ease",
      }}
    >
      <div
        style={{
          fontSize: "0.85rem",
          fontWeight: 600,
          marginBottom: "0.5rem",
        }}
      >
        {camera.name || camera.camera_id}
      </div>

      <label
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontSize: "0.85rem",
          color: "var(--text-muted, #888)",
          marginBottom: "0.4rem",
          cursor: saving ? "wait" : "pointer",
        }}
      >
        <span>Continuous 24/7</span>
        <input
          type="checkbox"
          checked={local.continuous_24_7}
          onChange={onToggleContinuous}
          disabled={saving}
        />
      </label>

      <label
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontSize: "0.85rem",
          color: "var(--text-muted, #888)",
          marginBottom: local.scheduled_recording ? "0.4rem" : 0,
          cursor: saving ? "wait" : "pointer",
        }}
      >
        <span>Scheduled Recording</span>
        <input
          type="checkbox"
          checked={local.scheduled_recording}
          onChange={onToggleScheduled}
          disabled={saving}
        />
      </label>

      {local.scheduled_recording && (
        <div
          style={{
            display: "flex",
            gap: "0.5rem",
            alignItems: "center",
            fontSize: "0.85rem",
            marginTop: "0.3rem",
          }}
        >
          <input
            type="time"
            value={local.scheduled_start || ""}
            onChange={(e) => onChangeTime("scheduled_start", e.target.value)}
            disabled={saving}
            style={{
              padding: "0.25rem 0.5rem",
              background: "var(--bg-secondary, #1a1a1a)",
              border: "1px solid var(--border, #333)",
              borderRadius: "4px",
              color: "var(--text-primary, #fff)",
              fontSize: "0.85rem",
            }}
          />
          <span style={{ color: "var(--text-muted, #888)" }}>to</span>
          <input
            type="time"
            value={local.scheduled_end || ""}
            onChange={(e) => onChangeTime("scheduled_end", e.target.value)}
            disabled={saving}
            style={{
              padding: "0.25rem 0.5rem",
              background: "var(--bg-secondary, #1a1a1a)",
              border: "1px solid var(--border, #333)",
              borderRadius: "4px",
              color: "var(--text-primary, #fff)",
              fontSize: "0.85rem",
            }}
          />
        </div>
      )}
    </div>
  )
}

export default CameraRecordingControls
