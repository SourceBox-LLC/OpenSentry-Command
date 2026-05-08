// Custom line-icons for the landing page Features grid.
// Replaces the emoji-as-icons pattern — emoji read as casual / hobbyist;
// consistent stroked SVG glyphs in soft brand-colour badges read as
// premium product.
//
// Style: 24px viewBox, 1.75 stroke, round line caps + joins, fill: none.
// All icons use stroke="currentColor" so the parent's CSS colour cascades
// (so a single icon can be tinted green, purple, amber, etc. by its host).

const baseProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  width: 24,
  height: 24,
}

export function CloudIcon(props) {
  return (
    <svg {...baseProps} {...props} aria-hidden="true">
      <path d="M17.5 19a4.5 4.5 0 1 0-1.5-8.74A6 6 0 1 0 5.5 14H6a4.5 4.5 0 0 0 0 5z" />
    </svg>
  )
}

export function ShieldLockIcon(props) {
  return (
    <svg {...baseProps} {...props} aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <rect x="9" y="11" width="6" height="5" rx="0.6" />
      <path d="M10.5 11V9.5a1.5 1.5 0 0 1 3 0V11" />
    </svg>
  )
}

export function MemoryIcon(props) {
  return (
    <svg {...baseProps} {...props} aria-hidden="true">
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <rect x="9" y="9" width="6" height="6" />
      <path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2" />
    </svg>
  )
}

export function UsersIcon(props) {
  return (
    <svg {...baseProps} {...props} aria-hidden="true">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  )
}

export function VideoIcon(props) {
  return (
    <svg {...baseProps} {...props} aria-hidden="true">
      <path d="m22 8-6 4 6 4V8z" />
      <rect x="2" y="6" width="14" height="12" rx="2" />
    </svg>
  )
}

export function KeyIcon(props) {
  return (
    <svg {...baseProps} {...props} aria-hidden="true">
      <circle cx="7.5" cy="15.5" r="5.5" />
      <path d="m21 2-9.6 9.6" />
      <path d="m15.5 7.5 3 3L22 7l-3-3" />
    </svg>
  )
}

export function CodeIcon(props) {
  return (
    <svg {...baseProps} {...props} aria-hidden="true">
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  )
}

export function ShieldCheckIcon(props) {
  return (
    <svg {...baseProps} {...props} aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <polyline points="9 12 11 14 15 10" />
    </svg>
  )
}
