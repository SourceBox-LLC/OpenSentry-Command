/**
 * Per-node storage usage bar shown on the Settings → Camera Nodes
 * card.  Reads CloudNode v0.1.41+ heartbeat-reported storage stats
 * (used/max/disk_free/disk_total) and renders:
 *
 *   - A bar showing used vs configured cap (max_size_gb).  100% means
 *     the retention loop is now actively deleting oldest segments to
 *     keep things at the cap — not a system error, just a "your node
 *     is at its allocated limit" indicator.
 *   - A separate red banner if the host's actual filesystem free
 *     space is below the 1 GiB safety floor.  When that fires,
 *     CloudNode pauses durable recording writes regardless of the
 *     cap, to avoid filling the host's disk.
 *
 * Renders nothing if the node hasn't reported stats yet (older
 * CloudNode, brand-new install) — better than an empty 0% bar that
 * lies about the data we don't have.
 */

const GIB = 1024 * 1024 * 1024
const SAFETY_FLOOR_BYTES = 1 * GIB

function formatGb(bytes) {
  if (!bytes && bytes !== 0) return "—"
  if (bytes < GIB) {
    return `${(bytes / (1024 * 1024)).toFixed(0)} MB`
  }
  return `${(bytes / GIB).toFixed(1)} GB`
}

function NodeStorageBar({ storage }) {
  if (!storage) return null

  const used = storage.used_bytes ?? 0
  const max = storage.max_bytes ?? 0
  const diskFree = storage.disk_free_bytes ?? 0
  const diskTotal = storage.disk_total_bytes ?? 0

  // 100% means "at cap" — clamp so the bar doesn't overflow visually
  // when the writer sneaks past the cap between retention ticks.
  const rawPct = max > 0 ? (used / max) * 100 : 0
  const displayPct = Math.min(rawPct, 100)
  const overCap = rawPct > 100
  // Color band: green < 75, amber 75-90, red 90+.  At-cap (>=100) is
  // not a failure — it's the retention loop doing its job — but it's
  // worth surfacing visually so the operator sees "this node is full,
  // recordings are being aged out" without having to read the number.
  const barClass = displayPct >= 90 ? "danger" : displayPct >= 75 ? "warn" : "ok"

  // Disk-free safety floor: independent signal.  Only show when we
  // actually have a reading (disk_free_bytes > 0 means sysinfo
  // identified the disk; 0 means "couldn't, hide the warning rather
  // than scream wolf").
  const diskCritical = diskFree > 0 && diskFree < SAFETY_FLOOR_BYTES

  return (
    <div className="node-storage" style={{ marginTop: "0.6rem" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          fontSize: "0.85rem",
          color: "var(--text-muted, #888)",
          marginBottom: "0.25rem",
        }}
      >
        <span>Storage</span>
        <span>
          {formatGb(used)} / {formatGb(max)}
          <span style={{ marginLeft: "0.5rem" }}>
            ({displayPct.toFixed(0)}%)
          </span>
        </span>
      </div>
      <div
        style={{
          height: "6px",
          width: "100%",
          background: "var(--bg-secondary, #1a1a1a)",
          borderRadius: "3px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${displayPct}%`,
            height: "100%",
            background:
              barClass === "danger"
                ? "var(--accent-red, #ef4444)"
                : barClass === "warn"
                  ? "var(--accent-amber, #f59e0b)"
                  : "var(--accent-green, #22c55e)",
            transition: "width 0.3s ease, background 0.3s ease",
          }}
        />
      </div>
      {overCap && (
        <p
          style={{
            fontSize: "0.78rem",
            color: "var(--text-muted, #888)",
            marginTop: "0.25rem",
            marginBottom: 0,
          }}
        >
          Over cap — retention is deleting oldest recordings to free space.
        </p>
      )}
      {diskTotal > 0 && (
        // Host disk subtitle — surfaces the actual filesystem state at all
        // times, not just when the safety floor trips.  Gives operators
        // context about how much headroom is on the host (e.g. cap is
        // 64 GB but only 30 GB of host disk is free → operator should
        // either lower the cap or upgrade disk).  Hidden when disk_total
        // is 0 (sysinfo couldn't identify the disk — Docker rootfs, FUSE)
        // since "0 / 0" is meaningless.
        <p
          style={{
            fontSize: "0.78rem",
            color: "var(--text-muted, #888)",
            marginTop: "0.35rem",
            marginBottom: 0,
          }}
        >
          Host disk: {formatGb(diskFree)} free of {formatGb(diskTotal)}
        </p>
      )}
      {diskCritical && (
        <p
          role="alert"
          style={{
            fontSize: "0.8rem",
            color: "var(--accent-red, #ef4444)",
            marginTop: "0.4rem",
            marginBottom: 0,
            padding: "0.4rem 0.6rem",
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid var(--accent-red, #ef4444)",
            borderRadius: "4px",
          }}
        >
          ⚠️ Host disk is critically low ({formatGb(diskFree)} free).
          Recording is paused on this node until space is freed.
        </p>
      )}
    </div>
  )
}

export default NodeStorageBar
