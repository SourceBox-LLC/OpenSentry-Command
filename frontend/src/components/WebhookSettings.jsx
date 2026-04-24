import { useState, useEffect, useCallback } from "react"
import { Link } from "react-router-dom"
import { useAuth } from "@clerk/clerk-react"
import {
  listOutboundWebhooks,
  createOutboundWebhook,
  updateOutboundWebhook,
  deleteOutboundWebhook,
  testOutboundWebhook,
} from "../services/api"

// Event kinds the backend supports. Must match the whitelist in
// app.api.webhooks_outbound.WebhookCreate._normalize_events or the
// create call 422s.
const EVENT_CHOICES = [
  { value: "motion", label: "Motion detected" },
  { value: "camera_online", label: "Camera online" },
  { value: "camera_offline", label: "Camera offline" },
  { value: "node_online", label: "Node online" },
  { value: "node_offline", label: "Node offline" },
]

function formatRelativeTime(iso) {
  if (!iso) return "never"
  const delta = Date.now() - new Date(iso).getTime()
  const secs = Math.floor(delta / 1000)
  if (secs < 60) return `${secs}s ago`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

/**
 * Settings section for outbound webhook endpoints (Pro Plus feature).
 *
 * Renders three states depending on the org's plan:
 *  1. Free / Pro  → upgrade pitch with inline CTA
 *  2. Pro Plus, no endpoints → empty-state + create form
 *  3. Pro Plus, ≥1 endpoint  → list + per-row test/toggle/delete controls
 *
 * The signing secret is returned exactly once when the endpoint is created;
 * we render it in a dismissable success banner with a copy-to-clipboard
 * button and remind the user it won't be shown again. This matches the
 * pattern used for CloudNode and MCP API keys.
 */
function WebhookSettings({ planInfo, onUpgrade, showToast }) {
  const { getToken } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [upgradeRequired, setUpgradeRequired] = useState(false)

  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState({ name: "", url: "", events: [] })
  const [creating, setCreating] = useState(false)
  // { name, url, events, signing_secret } — rendered in the success banner
  // immediately after create; cleared when dismissed.
  const [newlyCreated, setNewlyCreated] = useState(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const token = await getToken()
      const data = await listOutboundWebhooks(() => Promise.resolve(token))
      setRows(data.endpoints || [])
      setUpgradeRequired(!!data.upgrade_required)
    } catch (err) {
      console.error("[Webhooks] list failed:", err)
      showToast?.("Failed to load webhooks", "error")
    } finally {
      setLoading(false)
    }
  }, [getToken, showToast])

  useEffect(() => { load() }, [load])

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!form.name.trim() || !form.url.trim()) {
      showToast?.("Name and URL are required", "error")
      return
    }
    if (!form.url.startsWith("https://")) {
      showToast?.("URL must start with https://", "error")
      return
    }
    try {
      setCreating(true)
      const token = await getToken()
      const created = await createOutboundWebhook(() => Promise.resolve(token), {
        name: form.name.trim(),
        url: form.url.trim(),
        events: form.events,
      })
      setNewlyCreated(created)
      setForm({ name: "", url: "", events: [] })
      setFormOpen(false)
      await load()
    } catch (err) {
      console.error("[Webhooks] create failed:", err)
      showToast?.(err.message || "Create failed", "error")
    } finally {
      setCreating(false)
    }
  }

  const handleToggle = async (row) => {
    try {
      const token = await getToken()
      await updateOutboundWebhook(() => Promise.resolve(token), row.id, { enabled: !row.enabled })
      showToast?.(row.enabled ? "Webhook paused" : "Webhook resumed", "success")
      await load()
    } catch (err) {
      console.error("[Webhooks] toggle failed:", err)
      showToast?.(err.message || "Update failed", "error")
    }
  }

  const handleDelete = async (row) => {
    if (!window.confirm(`Delete webhook "${row.name}"? This cannot be undone.`)) return
    try {
      const token = await getToken()
      await deleteOutboundWebhook(() => Promise.resolve(token), row.id)
      showToast?.("Webhook deleted", "success")
      await load()
    } catch (err) {
      console.error("[Webhooks] delete failed:", err)
      showToast?.(err.message || "Delete failed", "error")
    }
  }

  const handleTest = async (row) => {
    try {
      const token = await getToken()
      await testOutboundWebhook(() => Promise.resolve(token), row.id)
      showToast?.("Test event queued — check your endpoint logs", "success")
      // Load after a short delay so the delivery has time to record.
      setTimeout(load, 2000)
    } catch (err) {
      console.error("[Webhooks] test failed:", err)
      showToast?.(err.message || "Test failed", "error")
    }
  }

  const toggleEvent = (value) => {
    setForm(prev => ({
      ...prev,
      events: prev.events.includes(value)
        ? prev.events.filter(v => v !== value)
        : [...prev.events, value],
    }))
  }

  const copySecret = (secret) => {
    navigator.clipboard?.writeText(secret).then(
      () => showToast?.("Signing secret copied to clipboard", "success"),
      () => showToast?.("Copy failed — select manually", "error"),
    )
  }

  if (loading) {
    return (
      <div className="settings-section">
        <h2>Outbound Webhooks</h2>
        <p className="section-description">Loading…</p>
      </div>
    )
  }

  if (upgradeRequired) {
    return (
      <div className="settings-section">
        <h2>Outbound Webhooks</h2>
        <p className="section-description">
          Push motion and camera events directly to your own HTTPS endpoint
          — integrate with PagerDuty, Zapier, your ticketing system, or
          home automation without opening a polling connection. Available
          on the <strong>Pro Plus</strong> plan.
        </p>
        <div className="webhook-upgrade-pitch">
          <ul className="security-bullets">
            <li>Every event is signed with HMAC-SHA256 — you verify with your copy of the secret</li>
            <li>Automatic retries with exponential backoff for transient 5xx errors</li>
            <li>Auto-disables after 20 consecutive failures so a dead URL doesn't burn your budget</li>
          </ul>
          <button className="btn btn-primary" onClick={onUpgrade}>
            Upgrade to Pro Plus
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="settings-section">
      <div className="section-header">
        <h2>Outbound Webhooks</h2>
        {!formOpen && (
          <button className="btn btn-primary btn-small" onClick={() => setFormOpen(true)}>
            + Add Endpoint
          </button>
        )}
      </div>
      <p className="section-description">
        Push events to your own HTTPS endpoint. Each request carries an
        <code> X-SourceBox-Signature</code> header (HMAC-SHA256) that you
        verify with your endpoint's signing secret.
      </p>

      {newlyCreated && (
        <div className="webhook-secret-banner" role="status">
          <div className="webhook-secret-banner-head">
            <strong>Endpoint created — save this signing secret now</strong>
            <button className="btn btn-secondary btn-small" onClick={() => setNewlyCreated(null)}>Dismiss</button>
          </div>
          <p>
            This secret is shown <em>once</em>. Use it to verify incoming
            deliveries. If you lose it, delete this endpoint and create a new one.
          </p>
          <div className="webhook-secret-value">
            <code>{newlyCreated.signing_secret}</code>
            <button className="btn btn-secondary btn-small" onClick={() => copySecret(newlyCreated.signing_secret)}>
              Copy
            </button>
          </div>
        </div>
      )}

      {formOpen && (
        <form className="webhook-form" onSubmit={handleCreate}>
          <div className="form-row">
            <label>
              Name
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. PagerDuty integration"
                maxLength={100}
                required
              />
            </label>
          </div>
          <div className="form-row">
            <label>
              URL
              <input
                type="url"
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
                placeholder="https://example.com/webhooks/sourcebox"
                maxLength={500}
                required
              />
            </label>
          </div>
          <fieldset className="webhook-events-fieldset">
            <legend>Event subscriptions (leave empty for all)</legend>
            <div className="webhook-event-grid">
              {EVENT_CHOICES.map(ev => (
                <label key={ev.value} className="webhook-event-choice">
                  <input
                    type="checkbox"
                    checked={form.events.includes(ev.value)}
                    onChange={() => toggleEvent(ev.value)}
                  />
                  <span>{ev.label}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="form-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setFormOpen(false)} disabled={creating}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={creating}>
              {creating ? "Creating…" : "Create Endpoint"}
            </button>
          </div>
        </form>
      )}

      {rows.length === 0 && !formOpen ? (
        <div className="empty-state-small">
          <p>No webhook endpoints yet. Add one to start pushing events to your own infrastructure.</p>
        </div>
      ) : (
        <ul className="webhook-list">
          {rows.map(row => (
            <li key={row.id} className={`webhook-item ${row.enabled ? "" : "webhook-item-disabled"}`}>
              <div className="webhook-item-head">
                <div className="webhook-item-name">
                  <strong>{row.name}</strong>
                  {!row.enabled && <span className="webhook-pill webhook-pill-paused">Paused</span>}
                  {row.consecutive_failures > 0 && row.enabled && (
                    <span className="webhook-pill webhook-pill-failing">
                      {row.consecutive_failures} failure{row.consecutive_failures === 1 ? "" : "s"}
                    </span>
                  )}
                </div>
                <div className="webhook-item-actions">
                  <button className="btn btn-secondary btn-small" onClick={() => handleTest(row)}>Test</button>
                  <button className="btn btn-secondary btn-small" onClick={() => handleToggle(row)}>
                    {row.enabled ? "Pause" : "Resume"}
                  </button>
                  <button className="btn btn-danger btn-small" onClick={() => handleDelete(row)}>Delete</button>
                </div>
              </div>
              <div className="webhook-item-url"><code>{row.url}</code></div>
              <div className="webhook-item-meta">
                <span>Events: {row.events.length === 0 ? "all" : row.events.join(", ")}</span>
                <span>·</span>
                <span>Last delivery: {formatRelativeTime(row.last_delivery_at)}</span>
                {row.last_delivery_status ? (
                  <>
                    <span>·</span>
                    <span className={row.last_delivery_status < 400 ? "webhook-status-ok" : "webhook-status-bad"}>
                      HTTP {row.last_delivery_status}
                    </span>
                  </>
                ) : null}
                {row.last_delivery_error && (
                  <>
                    <span>·</span>
                    <span className="webhook-status-bad" title={row.last_delivery_error}>
                      {row.last_delivery_error.slice(0, 60)}{row.last_delivery_error.length > 60 ? "…" : ""}
                    </span>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default WebhookSettings
