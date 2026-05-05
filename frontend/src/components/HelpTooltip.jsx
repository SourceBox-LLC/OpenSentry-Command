import { useEffect, useId, useRef, useState } from "react"

/*
 * Inline contextual-help icon.
 *
 * Renders a small "?" button next to a setting/control.  Hover or
 * focus reveals a popover with a short explanation; click toggles
 * the popover for touch devices that don't have hover.
 *
 * Use it where a setting's label alone isn't enough to explain what
 * it does — recording policy, MCP scope picker, default-off email
 * toggles, etc.  The goal is to cut "what does this mean?" support
 * tickets BEFORE they're written, by putting the answer one click
 * away from the question.
 *
 * Props:
 *   children  — the help body (markdown-ish JSX, kept short).  Two
 *               sentences max — anything longer should link out to
 *               /docs and use this just for the gist.
 *   docHref   — optional URL for a "Learn more →" link at the bottom
 *               of the popover.  Use #anchors into /docs when the
 *               linked content lives there already.
 *   label     — accessible label for the trigger button.  Defaults
 *               to "Help" but the parent should pass something like
 *               "Help: recording policy" so screen readers can
 *               distinguish multiple icons on the same page.
 *
 * Layout: the popover positions itself absolutely below the icon
 * and is clipped to the viewport via right-aligned defaults that
 * work for nav-rightside settings panels (the dominant layout).
 * For tighter columns, parents can wrap the icon in a relative
 * container and the popover will inherit the position.
 */
export default function HelpTooltip({ children, docHref, label = "Help" }) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef(null)
  const popoverId = useId()

  // Close on outside-click or Escape so the popover doesn't stick
  // open and obscure the page content.  Both events are scoped to
  // the document so we don't need to attach handlers to every
  // sibling element.
  useEffect(() => {
    if (!open) return
    const handleClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    const handleKey = (e) => {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", handleClick)
    document.addEventListener("keydown", handleKey)
    return () => {
      document.removeEventListener("mousedown", handleClick)
      document.removeEventListener("keydown", handleKey)
    }
  }, [open])

  return (
    <span className="help-tooltip" ref={containerRef}>
      <button
        type="button"
        className="help-tooltip-trigger"
        onClick={() => setOpen((v) => !v)}
        onMouseEnter={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        // Don't blur-close — losing focus to the popover content
        // (e.g. clicking the "Learn more" link) shouldn't dismiss
        // the popover before the click registers.
        aria-label={label}
        aria-expanded={open}
        aria-controls={popoverId}
      >
        ?
      </button>
      {open && (
        <div
          id={popoverId}
          className="help-tooltip-popover"
          role="tooltip"
          // Mouse-leave on the popover wrapper closes — the trigger
          // also gets re-rendered with onMouseEnter so a tight back-
          // and-forth between trigger and popover stays open.
          onMouseLeave={() => setOpen(false)}
        >
          <div className="help-tooltip-body">{children}</div>
          {docHref && (
            <a
              className="help-tooltip-doclink"
              href={docHref}
              target={docHref.startsWith("#") ? undefined : "_blank"}
              rel={docHref.startsWith("#") ? undefined : "noopener noreferrer"}
            >
              Learn more →
            </a>
          )}
        </div>
      )}
    </span>
  )
}
