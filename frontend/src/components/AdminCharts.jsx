// Lightweight visualisations for the admin dashboard's stat cards.
// Two components, both hand-rolled SVG / CSS — no charting library.
//
// BarList replaces "Top X" text rows (camera_id · 42, user · 137,
// tool_name · 8) with horizontal bars proportional to the max in
// the set.  Visual rhythm: label on top, count on the right, thin
// track underneath.
//
// DailyActivityChart replaces "2026-05-01: 37 / 2026-04-30: 67" text
// rows with vertical bars under MM-DD x-axis labels.  Uses
// currentColor so the SVG inherits its accent from CSS — keeps the
// component free of hard-coded palette references.

export function BarList({ items, accent = "green", emptyLabel = "No data", monoLabel = false }) {
  if (!items || items.length === 0) {
    return <div className="bar-list-empty">{emptyLabel}</div>
  }

  const max = Math.max(...items.map((i) => Number(i.count) || 0), 1)

  return (
    <ul className="bar-list" data-accent={accent}>
      {items.map((item, i) => {
        const count = Number(item.count) || 0
        const pct = (count / max) * 100
        return (
          <li key={item.key ?? i} className="bar-list-row">
            <div className="bar-list-row-head">
              <span
                className={`bar-list-label${monoLabel ? " bar-list-label-mono" : ""}`}
                title={item.label}
              >
                {item.label}
              </span>
              <span className="bar-list-count">{count.toLocaleString()}</span>
            </div>
            <div className="bar-list-track">
              <div className="bar-list-fill" style={{ width: `${pct}%` }} />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

export function DailyActivityChart({ data, accent = "green", emptyLabel = "No data" }) {
  if (!data || data.length === 0) {
    return <div className="daily-chart-empty">{emptyLabel}</div>
  }

  const sorted = [...data].sort((a, b) => (a.date || "").localeCompare(b.date || ""))
  const counts = sorted.map((d) => Number(d.count) || 0)
  const max = Math.max(...counts, 1)

  const width = 320
  const height = 112
  const pad = { top: 10, right: 6, bottom: 22, left: 6 }
  const innerW = width - pad.left - pad.right
  const innerH = height - pad.top - pad.bottom
  const slotW = innerW / sorted.length
  const barW = Math.min(slotW * 0.7, 36) // cap so 1-2 bars don't balloon
  const slotPad = (slotW - barW) / 2

  return (
    <svg
      role="img"
      aria-label="Daily activity"
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="daily-chart"
      data-accent={accent}
      preserveAspectRatio="none"
    >
      {/* Subtle baseline so empty days still feel anchored */}
      <line
        x1={pad.left}
        y1={pad.top + innerH + 0.5}
        x2={pad.left + innerW}
        y2={pad.top + innerH + 0.5}
        className="daily-chart-baseline"
      />
      {sorted.map((d, i) => {
        const c = counts[i]
        const h = c > 0 ? Math.max((c / max) * innerH, 3) : 0
        const x = pad.left + i * slotW + slotPad
        const y = pad.top + (innerH - h)
        const labelX = pad.left + i * slotW + slotW / 2
        const dayLabel = (d.date || "").slice(5) // MM-DD
        return (
          <g key={d.date || i}>
            <title>{`${d.date}: ${c.toLocaleString()}`}</title>
            {h > 0 && (
              <rect x={x} y={y} width={barW} height={h} fill="currentColor" rx="2" />
            )}
            <text
              x={labelX}
              y={pad.top + innerH + 14}
              textAnchor="middle"
              className="daily-chart-label"
            >
              {dayLabel}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
