import { useState, useEffect } from "react"
import { useAuth, useOrganization } from "@clerk/clerk-react"
import { getMcpKeys, createMcpKey, revokeMcpKey, getPlanInfo } from "../services/api"
import { useToasts } from "../hooks/useToasts.jsx"
import UpgradeModal from "../components/UpgradeModal.jsx"

const MCP_URL = `${window.location.origin}/mcp`

const TOOLS = [
  { name: "view_camera", desc: "See what a camera sees — returns a live JPEG snapshot", highlight: true },
  { name: "watch_camera", desc: "Take multiple snapshots over time to observe activity", highlight: true },
  { name: "list_cameras", desc: "List all cameras with status and codec info" },
  { name: "get_camera", desc: "Get details for a specific camera" },
  { name: "get_stream_url", desc: "Get a temporary HLS stream URL" },
  { name: "list_nodes", desc: "List camera nodes with status" },
  { name: "get_node", desc: "Get details for a specific node" },
  { name: "list_camera_groups", desc: "List camera groups" },
  { name: "create_camera_group", desc: "Create a new camera group" },
  { name: "assign_camera_to_group", desc: "Assign a camera to a group" },
  { name: "get_recording_settings", desc: "View current recording config" },
  { name: "update_recording_settings", desc: "Change recording settings" },
  { name: "get_stream_logs", desc: "View stream access history" },
  { name: "get_stream_stats", desc: "Get aggregated stream statistics" },
  { name: "get_system_status", desc: "System overview: cameras, nodes, plan" },
]

function McpPage() {
  const { getToken } = useAuth()
  const { organization } = useOrganization()
  const { showToast } = useToasts()

  const [planInfo, setPlanInfo] = useState(null)
  const [keys, setKeys] = useState([])
  const [keysLoading, setKeysLoading] = useState(false)
  const [newKeyName, setNewKeyName] = useState("")
  const [createdKey, setCreatedKey] = useState(null)
  const [creating, setCreating] = useState(false)
  const [copied, setCopied] = useState(null)
  const [revoking, setRevoking] = useState(null)
  const [showUpgrade, setShowUpgrade] = useState(false)

  useEffect(() => {
    if (organization) {
      loadPlanInfo()
      loadKeys()
    }
  }, [organization])

  const loadPlanInfo = async () => {
    try {
      const token = await getToken()
      const data = await getPlanInfo(() => Promise.resolve(token))
      setPlanInfo(data)
    } catch (err) {
      console.error("Failed to load plan info:", err)
    }
  }

  const loadKeys = async () => {
    setKeysLoading(true)
    try {
      const token = await getToken()
      const data = await getMcpKeys(() => Promise.resolve(token))
      setKeys(data)
    } catch (err) {
      console.error("Failed to load MCP keys:", err)
    } finally {
      setKeysLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!newKeyName.trim()) return
    setCreating(true)
    try {
      const token = await getToken()
      const data = await createMcpKey(() => Promise.resolve(token), newKeyName.trim())
      setCreatedKey(data.key)
      setNewKeyName("")
      await loadKeys()
      showToast("MCP API key created", "success")
    } catch (err) {
      showToast(err.message || "Failed to create key", "error")
    } finally {
      setCreating(false)
    }
  }

  const handleRevoke = async (keyId) => {
    setRevoking(keyId)
    try {
      const token = await getToken()
      await revokeMcpKey(() => Promise.resolve(token), keyId)
      await loadKeys()
      showToast("API key revoked", "success")
    } catch (err) {
      showToast(err.message || "Failed to revoke key", "error")
    } finally {
      setRevoking(null)
    }
  }

  const copyToClipboard = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(label)
      showToast("Copied to clipboard", "success")
      setTimeout(() => setCopied(null), 2000)
    } catch {
      showToast("Failed to copy", "error")
    }
  }

  const configJson = (key) => JSON.stringify({
    mcpServers: {
      opensentry: {
        type: "http",
        url: MCP_URL,
        headers: {
          Authorization: `Bearer ${key || "osc_your_key_here"}`
        }
      }
    }
  }, null, 2)

  const isPro = planInfo?.features?.includes("admin")

  if (!organization) {
    return (
      <div className="mcp-container">
        <h1 className="page-title">MCP Integration</h1>
        <p className="text-muted">Please select an organization.</p>
      </div>
    )
  }

  if (planInfo && !isPro) {
    return (
      <div className="mcp-container">
        <h1 className="page-title">MCP Integration</h1>

        <div className="mcp-locked-page">
          {/* Ambient glow */}
          <div className="mcp-glow mcp-glow-1" />
          <div className="mcp-glow mcp-glow-2" />

          <div className="mcp-locked-hero">
            <div className="mcp-locked-badge">PRO</div>
            <div className="mcp-locked-icon">{"</>"}</div>
            <h2>AI-Powered Camera Control</h2>
            <p>
              Give Claude Code, Cursor, or any MCP-compatible AI tool direct
              access to your cameras, nodes, and settings — all through
              natural language.
            </p>

            <div className="mcp-locked-examples">
              <div className="mcp-example">"Show me what the front door camera sees"</div>
              <div className="mcp-example">"Watch the garage cam for 30 seconds"</div>
              <div className="mcp-example">"List all my cameras and their status"</div>
            </div>

            <button className="mcp-upgrade-btn" onClick={() => setShowUpgrade(true)}>
              Unlock MCP Integration
            </button>
            <span className="mcp-upgrade-hint">Available on Pro and Business plans</span>
          </div>

          <div className="mcp-locked-tools">
            <h3><span>{TOOLS.length}</span> tools included with Pro</h3>
            <div className="mcp-tools-grid">
              {TOOLS.map((tool) => (
                <div key={tool.name} className={`mcp-tool-card mcp-tool-locked${tool.highlight ? " mcp-tool-visual" : ""}`}>
                  <code>{tool.name}</code>
                  <span>{tool.desc}</span>
                  {tool.highlight && <span className="mcp-tool-badge">VISUAL</span>}
                </div>
              ))}
            </div>
          </div>
        </div>

        <UpgradeModal
          isOpen={showUpgrade}
          onClose={() => setShowUpgrade(false)}
          feature="mcp"
          currentPlan={planInfo?.plan}
        />
      </div>
    )
  }

  return (
    <div className="mcp-container">
      <h1 className="page-title">MCP Integration</h1>

      <div className="mcp-hero">
        <div className="mcp-hero-icon">{"</>"}</div>
        <h2>AI-Powered Camera Control</h2>
        <p className="mcp-hero-desc">
          Connect Claude Code, Cursor, or any MCP-compatible AI tool directly
          to your OpenSentry cameras. Manage your entire security system
          through natural language.
        </p>
      </div>

      {/* Quick Start */}
      <div className="mcp-section">
        <h3>Quick Start</h3>
        <div className="mcp-steps">
          <div className="mcp-step">
            <span className="mcp-step-num">1</span>
            <div>
              <strong>Generate an API key</strong>
              <p>Create a key below — it's tied to your organization.</p>
            </div>
          </div>
          <div className="mcp-step">
            <span className="mcp-step-num">2</span>
            <div>
              <strong>Add to your AI tool</strong>
              <p>Copy the config and paste it into your Claude Code settings.</p>
            </div>
          </div>
          <div className="mcp-step">
            <span className="mcp-step-num">3</span>
            <div>
              <strong>Start using it</strong>
              <p>"List my cameras" or "take a snapshot on the garage cam"</p>
            </div>
          </div>
        </div>
      </div>

      {/* API Keys */}
      <div className="mcp-section">
        <h3>API Keys</h3>

        {createdKey && (
          <div className="mcp-key-created">
            <div className="mcp-key-created-header">
              <span className="mcp-key-created-icon">🔑</span>
              <strong>Key created — save it now!</strong>
            </div>
            <p className="mcp-key-warning">
              This is the only time you'll see this key. Copy it before closing.
            </p>
            <div className="mcp-key-display">
              <code>{createdKey}</code>
              <button
                className="btn btn-small btn-secondary"
                onClick={() => copyToClipboard(createdKey, "key")}
              >
                {copied === "key" ? "Copied!" : "Copy Key"}
              </button>
            </div>
            <button
              className="btn btn-small btn-secondary mcp-key-dismiss"
              onClick={() => setCreatedKey(null)}
            >
              I've saved it
            </button>
          </div>
        )}

        <div className="mcp-key-create">
          <input
            type="text"
            placeholder="Key name (e.g. 'Claude Code')"
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            className="mcp-key-input"
          />
          <button
            className="btn btn-primary"
            onClick={handleCreate}
            disabled={creating || !newKeyName.trim()}
          >
            {creating ? "Creating..." : "Generate Key"}
          </button>
        </div>

        {keysLoading ? (
          <div className="loading-spinner" />
        ) : keys.length > 0 ? (
          <div className="mcp-keys-list">
            {keys.map((k) => (
              <div key={k.id} className="mcp-key-item">
                <div className="mcp-key-info">
                  <span className="mcp-key-name">{k.name}</span>
                  <span className="mcp-key-meta">
                    Created {new Date(k.created_at).toLocaleDateString()}
                    {k.last_used_at && (
                      <> — Last used {new Date(k.last_used_at).toLocaleDateString()}</>
                    )}
                  </span>
                </div>
                <button
                  className="btn btn-small btn-danger"
                  onClick={() => handleRevoke(k.id)}
                  disabled={revoking === k.id}
                >
                  {revoking === k.id ? "Revoking..." : "Revoke"}
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-muted mcp-no-keys">No API keys yet. Generate one above to get started.</p>
        )}
      </div>

      {/* Connection Config */}
      <div className="mcp-section">
        <h3>Connection Config</h3>
        <p className="section-description">
          Add this to your Claude Code settings (<code>~/.claude.json</code>) or project <code>.mcp.json</code>:
        </p>
        <div className="mcp-config-block">
          <div className="mcp-config-header">
            <span>Claude Code / .mcp.json</span>
            <button
              className="btn btn-small btn-secondary"
              onClick={() => copyToClipboard(configJson(createdKey), "config")}
            >
              {copied === "config" ? "Copied!" : "Copy"}
            </button>
          </div>
          <pre className="mcp-config-code">{configJson(createdKey)}</pre>
        </div>

        <p className="mcp-config-hint">
          Or add via CLI: <code>claude mcp add --transport http opensentry {MCP_URL} --header "Authorization: Bearer osc_your_key"</code>
        </p>
      </div>

      {/* Available Tools */}
      <div className="mcp-section">
        <h3>Available Tools ({TOOLS.length})</h3>
        <div className="mcp-tools-grid">
          {TOOLS.map((tool) => (
            <div key={tool.name} className={`mcp-tool-card${tool.highlight ? " mcp-tool-visual" : ""}`}>
              <code>{tool.name}</code>
              <span>{tool.desc}</span>
              {tool.highlight && <span className="mcp-tool-badge">VISUAL</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default McpPage
