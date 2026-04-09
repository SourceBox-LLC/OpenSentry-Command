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
  return fetchWithAuth(`/api/camera/${cameraId}/group?group_id=${groupId}`, getToken, {
    method: "PUT"
  })
}

// Node management
export async function getNodes(getToken) {
  return fetchWithAuth("/api/nodes", getToken)
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

export async function createMcpKey(getToken, name) {
  return fetchWithAuth(`/api/mcp/keys?name=${encodeURIComponent(name)}`, getToken, {
    method: "POST"
  })
}

export async function revokeMcpKey(getToken, keyId) {
  return fetchWithAuth(`/api/mcp/keys/${keyId}`, getToken, {
    method: "DELETE"
  })
}