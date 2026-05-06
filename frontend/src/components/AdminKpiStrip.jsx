// KPI hero strip for the Admin dashboard — four glanceable cards at
// the top of the page so an admin sees the pulse of the org without
// having to scroll past five log tables. Reuses the same data the
// existing stats sections fetch (stream stats, MCP stats, planInfo)
// so it's free at the data layer; the visualisation is the upgrade.

function Sparkline({ data, color = "currentColor", width = 88, height = 28 }) {
  if (!data || data.length < 2) {
    // One or zero data points — show a flat line so the card still
    // composes with the others rather than collapsing.
    return (
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="kpi-sparkline" aria-hidden="true">
        <line x1="2" y1={height / 2} x2={width - 2} y2={height / 2} stroke={color} strokeWidth="1.25" strokeOpacity="0.35" strokeDasharray="2 2" />
      </svg>
    )
  }

  const sorted = [...data].sort((a, b) => (a.date || "").localeCompare(b.date || ""))
  const counts = sorted.map((d) => Number(d.count) || 0)
  const max = Math.max(...counts, 1)
  const min = 0
  const range = max - min || 1

  const pad = 3
  const stepX = (width - 2 * pad) / Math.max(counts.length - 1, 1)

  const coords = counts.map((c, i) => {
    const x = pad + i * stepX
    const y = height - pad - ((c - min) / range) * (height - 2 * pad)
    return [x, y]
  })

  const points = coords.map(([x, y]) => `${x},${y}`).join(" ")

  // Area fill under the line — closes the polyline back down to the
  // baseline so we get a soft gradient under the trend instead of a
  // bare stroke.
  const areaPath =
    `M ${coords[0][0]},${height - pad} ` +
    coords.map(([x, y]) => `L ${x},${y}`).join(" ") +
    ` L ${coords[coords.length - 1][0]},${height - pad} Z`

  const lastX = coords[coords.length - 1][0]
  const lastY = coords[coords.length - 1][1]
  const gradId = `kpi-spark-grad-${color.replace(/[^a-z0-9]/gi, "")}`

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="kpi-sparkline" aria-hidden="true">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradId})`} />
      <polyline fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" points={points} />
      <circle cx={lastX} cy={lastY} r="2.25" fill={color} />
    </svg>
  )
}

function KpiCard({ label, value, accent, icon, sparkData, sparkColor, footer, status }) {
  const display = value ?? 0
  return (
    <div className={`kpi-card kpi-card-${accent}`} data-status={status || "ok"}>
      <div className="kpi-card-head">
        <span className="kpi-card-label">{label}</span>
        <span className="kpi-card-icon" aria-hidden="true">{icon}</span>
      </div>
      <div className="kpi-card-value">{Number(display).toLocaleString()}</div>
      <div className="kpi-card-footer">
        {sparkData !== undefined ? (
          <Sparkline data={sparkData} color={sparkColor} />
        ) : (
          footer || <span className="kpi-card-footer-empty">&nbsp;</span>
        )}
      </div>
    </div>
  )
}

function AdminKpiStrip({ stats, mcpStats, planInfo, streamDays = 7, mcpDays = 7 }) {
  const cameras = planInfo?.usage?.cameras ?? 0
  const camerasLimit = planInfo?.limits?.max_cameras
  const camerasFooter =
    typeof camerasLimit === "number" && camerasLimit > 0 ? (
      <span className="kpi-card-meter">
        <span className="kpi-card-meter-bar">
          <span
            className="kpi-card-meter-fill"
            style={{ width: `${Math.min(100, (cameras / camerasLimit) * 100)}%` }}
          />
        </span>
        <span className="kpi-card-meter-label">
          of {camerasLimit >= 999 ? "∞" : camerasLimit}
        </span>
      </span>
    ) : null

  const totalErrors = mcpStats?.total_errors ?? 0
  const errorStatus = totalErrors === 0 ? "ok" : totalErrors < 5 ? "warn" : "critical"
  const errorFooter = (
    <span className={`kpi-card-pill kpi-card-pill-${errorStatus}`}>
      {totalErrors === 0 ? "All clear" : totalErrors === 1 ? "1 failure" : `${totalErrors} failures`}
    </span>
  )

  // CSS variables — single source of truth for spark colours so they
  // stay in sync with the card accent border.
  const COLORS = {
    green: "rgb(34, 197, 94)",
    purple: "rgb(168, 85, 247)",
    blue: "rgb(59, 130, 246)",
    amber: "rgb(245, 158, 11)",
    red: "rgb(239, 68, 68)",
  }

  return (
    <div className="admin-kpi-strip">
      <KpiCard
        label={`Stream views · ${streamDays}d`}
        value={stats?.total_accesses}
        accent="green"
        icon="📺"
        sparkData={stats?.by_day}
        sparkColor={COLORS.green}
      />
      <KpiCard
        label={`MCP calls · ${mcpDays}d`}
        value={mcpStats?.total_calls}
        accent="purple"
        icon="🤖"
        sparkData={mcpStats?.by_day}
        sparkColor={COLORS.purple}
      />
      <KpiCard
        label="Registered cameras"
        value={cameras}
        accent="blue"
        icon="📹"
        footer={camerasFooter}
      />
      <KpiCard
        label={`MCP errors · ${mcpDays}d`}
        value={totalErrors}
        accent={errorStatus === "ok" ? "green" : errorStatus === "warn" ? "amber" : "red"}
        icon="⚠️"
        status={errorStatus}
        footer={errorFooter}
      />
    </div>
  )
}

export default AdminKpiStrip
