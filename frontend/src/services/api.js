const API_URL = import.meta.env.VITE_API_URL || ""

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
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `Request failed with status ${response.status}`)
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

export async function updateRecordingSettings(getToken, settings) {
  return fetchWithAuth("/api/settings/recording", getToken, {
    method: "POST",
    body: JSON.stringify(settings)
  })
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

export async function assignCameraGroup(getToken, cameraId, groupId) {
  return fetchWithAuth(`/api/cameras/${cameraId}/group?group_id=${groupId}`, getToken, {
    method: "PUT"
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