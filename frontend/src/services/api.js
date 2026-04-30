const API_URL = import.meta.env.VITE_API_URL || ""

/**
 * Parse a non-2xx response body into a usable Error.
 *
 * Three shapes exist on the wire today; the parser handles each cleanly
 * so consumers never see "[object Object]" in a toast regardless of
 * which backend pattern produced the response:
 *
 *   1. ApiError envelope — ``{detail: {error, message, ...extras}}``
 *      (see backend/app/core/errors.py — also matches the existing 402
 *      plan-limit-hit body and the new 422 validation handler)
 *   2. Plain string detail — ``{detail: "string"}``
 *      (most legacy ``raise HTTPException(detail="...")`` sites)
 *   3. Top-level envelope without ``detail`` —
 *      ``{error, message, ...}``
 *      (rate_limit_exceeded_handler in main.py emits this shape directly
 *      via JSONResponse rather than HTTPException)
 *
 * Plus the catch-all "no body / empty / non-JSON" fallback.
 *
 * The returned Error always has:
 *   - .message  — human-readable, ready to drop in a toast
 *   - .code     — machine-readable string when available, else null
 *                 (call sites can do ``if (e.code === "plan_limit_hit")``)
 *   - .status   — the HTTP status code
 *   - .detail   — the raw structured detail when one was sent, so
 *                 callers that branch on extra fields (plan,
 *                 max_cameras, etc.) can read them directly
 */
function parseErrorBody(body, status) {
  const detail = body?.detail

  // Shape 1: ApiError-style structured envelope under .detail
  if (detail && typeof detail === "object" && !Array.isArray(detail) && detail.message) {
    const err = new Error(detail.message)
    err.code = detail.error ?? null
    err.detail = detail
    err.status = status
    return err
  }

  // Shape 2: plain-string detail (legacy ``raise HTTPException`` pattern)
  if (typeof detail === "string") {
    const err = new Error(detail)
    err.code = null
    err.detail = null
    err.status = status
    return err
  }

  // Pydantic 422 fallback: array of {loc, msg, type}. Should be rare now
  // that main.py rewrites 422s through the validation handler, but
  // in-flight deploys (and the dev server when the handler hasn't
  // reloaded yet) can still surface this — handle defensively.
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] || {}
    const loc = Array.isArray(first.loc)
      ? first.loc.filter((p) => p !== "body").join(".")
      : ""
    const msg = first.msg || "Validation failed"
    const err = new Error(loc ? `${msg} (${loc})` : msg)
    err.code = "validation_failed"
    err.detail = { errors: detail }
    err.status = status
    return err
  }

  // Shape 3: top-level envelope without .detail (rate-limit handler).
  // The body itself carries error/message at the top.
  if (body && typeof body === "object" && body.message) {
    const err = new Error(body.message)
    err.code = body.error ?? null
    err.detail = body
    err.status = status
    return err
  }

  // Last-resort fallback: nothing useful in the body at all.
  const err = new Error(`Request failed with status ${status}`)
  err.code = null
  err.detail = null
  err.status = status
  return err
}

export async function fetchWithAuth(endpoint, getToken, options = {}) {
  const token = getToken ? await getToken() : null

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  let response
  try {
    response = await fetch(
      `${API_URL}${endpoint}`,
      {
        ...options,
        headers
      }
    )
  } catch (fetchError) {
    console.error("[API] Fetch error:", fetchError)
    throw fetchError
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw parseErrorBody(body, response.status)
  }

  if (response.status === 204) {
    return null
  }

  return await response.json()
}

export async function getCameras(getToken) {
  return fetchWithAuth("/api/cameras", getToken)
}

export async function getSettings(getToken) {
  return fetchWithAuth("/api/settings", getToken)
}

// Per-camera recording policy (v0.1.43+).  Replaced the org-level
// updateRecordingSettings, which was wired to a backend endpoint that
// persisted but never actually drove recording.  PATCH semantics —
// only the fields you pass get updated.
export async function updateCameraRecordingPolicy(getToken, cameraId, policy) {
  return fetchWithAuth(
    `/api/cameras/${encodeURIComponent(cameraId)}/recording-settings`,
    getToken,
    {
      method: "PATCH",
      body: JSON.stringify(policy),
    },
  )
}

export async function updateNotificationSettings(getToken, settings) {
  return fetchWithAuth("/api/settings/notifications", getToken, {
    method: "POST",
    body: JSON.stringify(settings)
  })
}

export async function getCameraGroups(getToken) {
  return fetchWithAuth("/api/camera-groups", getToken)
}

export async function createCameraGroup(getToken, name, color, icon) {
  return fetchWithAuth("/api/camera-groups", getToken, {
    method: "POST",
    body: JSON.stringify({ name, color, icon })
  })
}

export async function deleteCameraGroup(getToken, groupId) {
  return fetchWithAuth(`/api/camera-groups/${groupId}`, getToken, {
    method: "DELETE"
  })
}

// Node management
export async function getNodes(getToken) {
  return fetchWithAuth("/api/nodes", getToken)
}

export async function getNode(getToken, nodeId) {
  return fetchWithAuth(`/api/nodes/${nodeId}`, getToken)
}

export async function createNode(getToken, name) {
  return fetchWithAuth("/api/nodes", getToken, {
    method: "POST",
    body: JSON.stringify({ name })
  })
}

export async function rotateNodeKey(getToken, nodeId) {
  return fetchWithAuth(`/api/nodes/${nodeId}/rotate-key`, getToken, {
    method: "POST"
  })
}

export async function deleteNode(getToken, nodeId) {
  return fetchWithAuth(`/api/nodes/${nodeId}`, getToken, {
    method: "DELETE"
  })
}

// Snapshot (saved on the camera node)
export async function requestSnapshot(getToken, cameraId) {
  return fetchWithAuth(`/api/cameras/${cameraId}/snapshot`, getToken, {
    method: "POST"
  })
}

// Recording (start/stop on the camera node)
export async function setRecording(getToken, cameraId, recording) {
  return fetchWithAuth(`/api/cameras/${cameraId}/recording`, getToken, {
    method: "POST",
    body: JSON.stringify({ recording })
  })
}

// Audit logs (admin only)
export async function getStreamLogs(getToken, params = {}) {
  const queryString = new URLSearchParams(
    Object.entries(params).filter(([_, v]) => v != null)
  ).toString()
  return fetchWithAuth(`/api/audit/stream-logs?${queryString}`, getToken)
}

export async function getStreamStats(getToken, days = 7) {
  return fetchWithAuth(`/api/audit/stream-logs/stats?days=${days}`, getToken)
}

// Plan info
export async function getPlanInfo(getToken) {
  return fetchWithAuth("/api/nodes/plan", getToken)
}

// Danger Zone
export async function wipeStreamLogs(getToken) {
  return fetchWithAuth("/api/settings/danger/wipe-logs", getToken, {
    method: "POST"
  })
}

export async function fullReset(getToken) {
  return fetchWithAuth("/api/settings/danger/full-reset", getToken, {
    method: "POST"
  })
}

// MCP API Keys
export async function getMcpKeys(getToken) {
  return fetchWithAuth("/api/mcp/keys", getToken)
}

export async function createMcpKey(getToken, { name, scopeMode = "all", scopeTools = null } = {}) {
  const body = { name, scope_mode: scopeMode }
  if (scopeMode === "custom") {
    body.scope_tools = Array.isArray(scopeTools) ? scopeTools : []
  }
  return fetchWithAuth(`/api/mcp/keys`, getToken, {
    method: "POST",
    body: JSON.stringify(body)
  })
}

export async function revokeMcpKey(getToken, keyId) {
  return fetchWithAuth(`/api/mcp/keys/${keyId}`, getToken, {
    method: "DELETE"
  })
}

export async function getMcpToolCatalog(getToken) {
  return fetchWithAuth(`/api/mcp/tools`, getToken)
}

// MCP Activity
export async function getMcpActivity(getToken, limit = 50) {
  return fetchWithAuth(`/api/mcp/activity/recent?limit=${limit}`, getToken)
}

export async function getMcpSessions(getToken) {
  return fetchWithAuth("/api/mcp/activity/sessions", getToken)
}

export async function getMcpStats(getToken) {
  return fetchWithAuth("/api/mcp/activity/stats", getToken)
}

// MCP Activity Logs (DB-backed, for admin dashboard)
export async function getMcpLogs(getToken, params = {}) {
  const queryString = new URLSearchParams(
    Object.entries(params).filter(([_, v]) => v != null && v !== "")
  ).toString()
  return fetchWithAuth(`/api/mcp/activity/logs?${queryString}`, getToken)
}

export async function getMcpLogStats(getToken, days = 7) {
  return fetchWithAuth(`/api/mcp/activity/logs/stats?days=${days}`, getToken)
}

// AI-generated incident reports
export async function getIncidents(getToken, params = {}) {
  const queryString = new URLSearchParams(
    Object.entries(params).filter(([_, v]) => v != null && v !== "")
  ).toString()
  const suffix = queryString ? `?${queryString}` : ""
  return fetchWithAuth(`/api/incidents${suffix}`, getToken)
}

export async function getIncidentCounts(getToken) {
  return fetchWithAuth("/api/incidents/counts", getToken)
}

export async function getIncident(getToken, incidentId) {
  return fetchWithAuth(`/api/incidents/${incidentId}`, getToken)
}

export async function patchIncident(getToken, incidentId, patch) {
  return fetchWithAuth(`/api/incidents/${incidentId}`, getToken, {
    method: "PATCH",
    body: JSON.stringify(patch),
  })
}

export async function deleteIncident(getToken, incidentId) {
  return fetchWithAuth(`/api/incidents/${incidentId}`, getToken, {
    method: "DELETE",
  })
}

// Returns a Blob URL for an evidence snapshot. Caller must URL.revokeObjectURL when done.
export async function fetchIncidentEvidenceBlobUrl(getToken, incidentId, evidenceId) {
  const token = getToken ? await getToken() : null
  const headers = {}
  if (token) headers["Authorization"] = `Bearer ${token}`
  const response = await fetch(
    `${API_URL}/api/incidents/${incidentId}/evidence/${evidenceId}`,
    { headers }
  )
  if (!response.ok) {
    throw new Error(`Failed to load evidence (${response.status})`)
  }
  const blob = await response.blob()
  return URL.createObjectURL(blob)
}

// Absolute URL to the synthetic HLS playlist for a clip evidence item.
// hls.js loads this and resolves the segment URL inside it (which points back
// at the regular blob endpoint). Auth is added via xhrSetup, same as the
// live HlsPlayer.
export function incidentEvidencePlaylistUrl(incidentId, evidenceId) {
  return `${API_URL}/api/incidents/${incidentId}/evidence/${evidenceId}/playlist.m3u8`
}

// ── Notifications (bell inbox) ─────────────────────────────────────

export async function getNotifications(getToken, params = {}) {
  const queryString = new URLSearchParams(
    Object.entries(params).filter(([_, v]) => v != null && v !== "")
  ).toString()
  const suffix = queryString ? `?${queryString}` : ""
  return fetchWithAuth(`/api/notifications${suffix}`, getToken)
}

export async function getUnreadNotificationCount(getToken) {
  return fetchWithAuth("/api/notifications/unread-count", getToken)
}

export async function markNotificationsViewed(getToken) {
  return fetchWithAuth("/api/notifications/mark-viewed", getToken, {
    method: "POST",
  })
}

export async function clearAllNotifications(getToken) {
  return fetchWithAuth("/api/notifications/clear-all", getToken, {
    method: "POST",
  })
}