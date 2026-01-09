/**
 * OpenSentry Command Center - Main JavaScript
 */

// Toast notification system
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <div class="toast-icon">${type === 'success' ? '✓' : '✕'}</div>
        <div class="toast-message">${message}</div>
    `;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Wait for camera to be ready (streaming status) before proceeding
async function waitForCameraReady(cameraId, maxAttempts = 10) {
    for (let i = 0; i < maxAttempts; i++) {
        try {
            const response = await fetch('/api/cameras');
            const cameras = await response.json();
            if (cameras[cameraId] && cameras[cameraId].status === 'streaming') {
                // Add extra delay for backend stream to fully establish
                await new Promise(resolve => setTimeout(resolve, 500));
                return true;
            }
        } catch (e) {
            console.error('Error checking camera status:', e);
        }
        await new Promise(resolve => setTimeout(resolve, 500));
    }
    return false; // Timeout - proceed anyway
}

// Refresh video feed for a camera
function refreshFeed(cameraId) {
    const img = document.getElementById(`feed-${cameraId}`);
    const container = document.getElementById(`feed-container-${cameraId}`);
    
    if (img && container) {
        // Reset displayed flag so onFeedLoad can run again
        feedDisplayed[cameraId] = false;
        
        // Hide video and overlay, recreate loading element
        img.style.display = 'none';
        const overlay = container.querySelector('.feed-overlay');
        if (overlay) overlay.style.display = 'none';
        
        // Recreate loading element if it was removed
        let loading = container.querySelector('.feed-loading');
        if (!loading) {
            loading = document.createElement('div');
            loading.className = 'feed-loading';
            loading.id = `feed-loading-${cameraId}`;
            loading.innerHTML = `
                <div class="loading-spinner"></div>
                <span>Connecting to stream...</span>
            `;
            container.insertBefore(loading, container.firstChild);
        } else {
            // Reset loading state
            loading.classList.remove('reconnecting', 'error');
            loading.innerHTML = `
                <div class="loading-spinner"></div>
                <span>Connecting to stream...</span>
            `;
        }
        
        // Re-attach event handlers and reload stream
        const baseSrc = img.dataset.src || img.src.split('?')[0];
        img.onload = () => onFeedLoad(cameraId);
        img.onerror = () => onFeedError(cameraId);
        img.src = `${baseSrc}?t=${Date.now()}`;
        
        // Fallback: if onload doesn't fire within 3s, try to show video anyway
        setTimeout(() => {
            if (!feedDisplayed[cameraId]) {
                const loading = container.querySelector('.feed-loading');
                if (loading) loading.remove();
                img.style.cssText = 'display: block !important; visibility: visible !important;';
                const overlay = container.querySelector('.feed-overlay');
                if (overlay) overlay.style.cssText = 'display: flex !important; visibility: visible !important;';
                feedDisplayed[cameraId] = true;
            }
        }, 3000);
    }
}

// Handle feed load success
function onFeedLoad(cameraId) {
    // Only process once per feed to avoid redundant DOM updates
    if (feedDisplayed[cameraId]) return;
    
    const img = document.getElementById(`feed-${cameraId}`);
    if (!img) return;
    
    // Navigate from img to its parent container, then find siblings
    const container = img.parentElement;
    if (!container) return;
    
    // Find loading and overlay within the SAME container as the img
    const loading = container.querySelector('.feed-loading');
    const overlay = container.querySelector('.feed-overlay');
    
    // Check if image actually has content (naturalWidth > 0 means frames are arriving)
    if (img.naturalWidth === 0) {
        // Check again in 500ms
        setTimeout(() => {
            feedDisplayed[cameraId] = false;
            onFeedLoad(cameraId);
        }, 500);
        return;
    }
    
    // Check if this was a reconnection (had previous retries)
    const wasReconnecting = retryCount[cameraId] > 0;
    
    retryCount[cameraId] = 0;
    feedDisplayed[cameraId] = true;
    
    // Clear offline/reconnecting states from card
    const card = document.querySelector(`.camera-card[data-camera-id="${cameraId}"]`);
    if (card) {
        card.classList.remove('offline', 'reconnecting');
    }
    
    // Remove loading element and show video
    if (loading) loading.remove();
    img.style.cssText = 'display: block !important; visibility: visible !important;';
    if (overlay) overlay.style.cssText = 'display: flex !important; visibility: visible !important;';
    
    // Show reconnection success message
    if (wasReconnecting) {
        showToast(`Camera ${cameraId} reconnected`, 'success');
    }
}

// Track retry counts per camera
const retryCount = {};
const maxRetries = 3;

// Track which feeds have been successfully shown (to prevent redundant onload calls)
const feedDisplayed = {};

// Handle feed load error - retry with backoff
function onFeedError(cameraId) {
    const loading = document.getElementById(`feed-loading-${cameraId}`);
    const card = document.querySelector(`.camera-card[data-camera-id="${cameraId}"]`);
    retryCount[cameraId] = (retryCount[cameraId] || 0) + 1;
    
    if (retryCount[cameraId] <= maxRetries) {
        // Show reconnecting state
        if (loading) {
            loading.classList.add('reconnecting');
            loading.classList.remove('error');
            loading.innerHTML = `
                <div class="loading-spinner"></div>
                <span>Reconnecting...</span>
                <span class="retry-info">Attempt ${retryCount[cameraId]} of ${maxRetries}</span>
            `;
        }
        if (card) {
            card.classList.add('reconnecting');
            card.classList.remove('offline');
        }
        
        // Exponential backoff: 5s, 10s, 15s
        const delay = retryCount[cameraId] * 5000;
        setTimeout(() => refreshFeed(cameraId), delay);
    } else {
        // Show error state
        if (loading) {
            loading.classList.remove('reconnecting');
            loading.classList.add('error');
            loading.innerHTML = `
                <div class="status-icon">📡</div>
                <span>Stream unavailable</span>
                <span class="retry-info">Camera may be offline or starting up</span>
            `;
        }
        if (card) {
            card.classList.remove('reconnecting');
            card.classList.add('offline');
        }
    }
}

// Reset retry count when manually refreshing
function resetRetry(cameraId) {
    retryCount[cameraId] = 0;
}

// Track recording state per camera
const recordingState = {};

// Take snapshot from camera
async function takeSnapshot(cameraId) {
    try {
        const response = await fetch(`/api/camera/${cameraId}/snapshot?save=true`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            showToast(`Snapshot saved: ${data.filename}`, 'success');
        } else {
            showToast(`Error: ${data.error}`, 'error');
        }
    } catch (err) {
        console.error('Failed to take snapshot:', err);
        showToast('Failed to take snapshot', 'error');
    }
}

// Toggle recording on/off
async function toggleRecording(cameraId) {
    const btn = document.getElementById(`record-btn-${cameraId}`);
    const isRecording = recordingState[cameraId];
    
    try {
        const endpoint = isRecording ? 'stop' : 'start';
        const response = await fetch(`/api/camera/${cameraId}/recording/${endpoint}`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success || data.filename) {
            recordingState[cameraId] = !isRecording;
            
            if (recordingState[cameraId]) {
                btn.classList.add('recording');
                btn.innerHTML = `
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12"/></svg>
                    Stop
                `;
                showToast(`Recording started: ${data.filename}`, 'success');
            } else {
                btn.classList.remove('recording');
                btn.innerHTML = `
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="8"/></svg>
                    Record
                `;
                showToast(`Recording saved: ${data.filename} (${data.duration}s)`, 'success');
            }
        } else {
            showToast(`Error: ${data.error}`, 'error');
        }
    } catch (err) {
        console.error('Failed to toggle recording:', err);
        showToast('Failed to toggle recording', 'error');
    }
}

// Send command to camera via REST API
async function sendCommand(cameraId, command) {
    try {
        const response = await fetch(`/api/camera/${cameraId}/command`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command: command })
        });

        const data = await response.json();

        if (data.success) {
            showToast(`Command '${command}' sent to ${cameraId}`, 'success');
            // Refresh feed after start command - wait for camera to be streaming first
            if (command === 'start') {
                waitForCameraReady(cameraId, 10).then(() => {
                    resetRetry(cameraId);
                    refreshFeed(cameraId);
                });
            }
        } else {
            showToast(`Error: ${data.error}`, 'error');
        }
    } catch (err) {
        console.error('Failed to send command:', err);
        showToast('Failed to send command', 'error');
    }
}

// Track known cameras - initialize with any server-rendered cards
const knownCameras = new Set();

// Track previous status per camera to detect changes
const previousStatus = {};

// Create camera card HTML
function createCameraCard(cameraId, info) {
    const card = document.createElement('div');
    card.className = 'camera-card';
    card.dataset.cameraId = cameraId;
    card.innerHTML = `
        <div class="camera-header">
            <div class="camera-info">
                <div class="camera-icon">📹</div>
                <div class="camera-details">
                    <h3>${info.name}</h3>
                    <span>${cameraId}</span>
                </div>
            </div>
            <div class="status-badge ${info.status}" id="status-${cameraId}">
                <span class="dot"></span>
                <span class="status-text">${info.status}</span>
            </div>
        </div>
        <div class="camera-feed-container" id="feed-container-${cameraId}">
            <div class="feed-loading" id="feed-loading-${cameraId}">
                <div class="loading-spinner"></div>
                <span>Connecting to stream...</span>
            </div>
            <img class="camera-feed" id="feed-${cameraId}" data-src="/video_feed/${cameraId}" alt="${info.name}">
            <div class="feed-overlay" id="feed-overlay-${cameraId}">
                <span class="feed-tag live">LIVE</span>
                <span class="feed-tag">HD</span>
            </div>
        </div>
        <div class="camera-controls">
            <button class="btn btn-start" onclick="sendCommand('${cameraId}', 'start')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                Start
            </button>
            <button class="btn btn-stop" onclick="sendCommand('${cameraId}', 'stop')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                Pause
            </button>
            <button class="btn btn-snapshot" onclick="takeSnapshot('${cameraId}')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="3.2"/><path d="M9 2L7.17 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2h-3.17L15 2H9zm3 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5z"/></svg>
                Snapshot
            </button>
            <button class="btn btn-record" id="record-btn-${cameraId}" onclick="toggleRecording('${cameraId}')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="8"/></svg>
                Record
            </button>
            <button class="btn btn-shutdown" onclick="sendCommand('${cameraId}', 'shutdown')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.58-5.42L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z"/></svg>
                Shutdown
            </button>
        </div>
    `;
    return card;
}

// Initialize feed for a newly added camera
function initializeFeed(cameraId) {
    const img = document.getElementById(`feed-${cameraId}`);
    if (img && img.dataset.src) {
        img.onload = () => onFeedLoad(cameraId);
        img.onerror = () => onFeedError(cameraId);
        img.src = `${img.dataset.src}?t=${Date.now()}`;
    }
}

// Poll for camera status updates
async function updateStatus() {
    try {
        const response = await fetch('/api/cameras');
        const cameras = await response.json();

        const emptyState = document.getElementById('empty-state');
        const cameraGrid = document.getElementById('camera-grid');
        const cameraCount = Object.keys(cameras).length;

        // Show/hide empty state
        if (cameraCount === 0) {
            emptyState.classList.remove('hidden');
        } else {
            emptyState.classList.add('hidden');
        }

        let activeCount = 0;
        let streamingCount = 0;

        for (const [cameraId, info] of Object.entries(cameras)) {
            // Add new camera card if not already present
            if (!knownCameras.has(cameraId)) {
                knownCameras.add(cameraId);
                const card = createCameraCard(cameraId, info);
                cameraGrid.appendChild(card);
                // Initialize feed after card is added
                setTimeout(() => initializeFeed(cameraId), 100);
                showToast(`Camera discovered: ${info.name}`, 'success');
                
            }

            // Update status
            const statusEl = document.getElementById(`status-${cameraId}`);
            if (statusEl) {
                const textEl = statusEl.querySelector('.status-text');
                if (textEl) textEl.textContent = info.status;
                statusEl.className = `status-badge ${info.status}`;
            }

            // Handle status changes
            const prevStatus = previousStatus[cameraId];
            const retriesExhausted = (retryCount[cameraId] || 0) > maxRetries;
            const card = document.querySelector(`.camera-card[data-camera-id="${cameraId}"]`);
            
            // Camera went offline
            if (info.status === 'offline' && prevStatus !== 'offline') {
                showToast(`Camera ${info.name} went offline`, 'error');
                if (card) card.classList.add('offline');
            }
            
            // Camera came back online - auto-refresh if retries were exhausted
            if (info.status === 'streaming' && prevStatus !== 'streaming' && retriesExhausted) {
                resetRetry(cameraId);
                refreshFeed(cameraId);
            }
            
            // Clear offline state when camera is back
            if (info.status !== 'offline' && prevStatus === 'offline') {
                if (card) card.classList.remove('offline');
                showToast(`Camera ${info.name} is back online`, 'success');
            }
            
            previousStatus[cameraId] = info.status;

            if (info.status === 'streaming' || info.status === 'online' || info.status === 'discovered') activeCount++;
            if (info.status === 'streaming') streamingCount++;
        }

        // Update total nodes stat
        document.getElementById('stat-total').textContent = cameraCount;

        // Update stats
        document.getElementById('stat-active').textContent = activeCount;
        document.getElementById('stat-streaming').textContent = streamingCount;

        // Update system status
        const systemStat = document.getElementById('stat-system');
        if (streamingCount > 0) {
            systemStat.textContent = 'Active';
            systemStat.className = 'stat-value green';
        } else if (activeCount > 0) {
            systemStat.textContent = 'Ready';
            systemStat.className = 'stat-value amber';
        } else {
            systemStat.textContent = 'Idle';
            systemStat.className = 'stat-value blue';
        }

        // Update MQTT/Nodes status
        const mqttDot = document.getElementById('mqtt-dot');
        const mqttText = document.getElementById('mqtt-text');
        const nodesDot = document.getElementById('nodes-dot');
        const nodesCount = document.getElementById('nodes-count');

        const anyOnline = Object.values(cameras).some(c =>
            c.status !== 'unknown' && c.last_seen !== null
        );

        if (anyOnline) {
            mqttDot.className = 'status-dot';
            mqttText.textContent = 'MQTT Connected';
            nodesDot.className = 'status-dot';
            nodesCount.textContent = `${activeCount} Node${activeCount !== 1 ? 's' : ''} Online`;
        } else {
            mqttDot.className = 'status-dot warning';
            mqttText.textContent = 'MQTT Waiting...';
            nodesDot.className = 'status-dot error';
            nodesCount.textContent = '0 Nodes Online';
        }
    } catch (err) {
        console.error('Failed to fetch status:', err);
    }
}

// Initialize application
function initializeApp() {
    // Initialize known cameras from server-rendered cards
    document.querySelectorAll('.camera-card[data-camera-id]').forEach(card => {
        knownCameras.add(card.dataset.cameraId);
    });

    // Initialize all feeds on page load
    document.querySelectorAll('.camera-feed').forEach(img => {
        const cameraId = img.id.replace('feed-', '');
        
        img.onload = () => onFeedLoad(cameraId);
        img.onerror = () => onFeedError(cameraId);
        
        // Start loading the feed
        if (img.dataset.src) {
            img.src = `${img.dataset.src}?t=${Date.now()}`;
        }
    });

    // Start polling for status updates
    setInterval(updateStatus, 2000);
    updateStatus();
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', initializeApp);
