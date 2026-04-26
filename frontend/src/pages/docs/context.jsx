// Shared state for the split DocsPage.
//
// The pre-split DocsPage held three pieces of state that >half of the section
// bodies needed: the user's currently-selected OS (drives the install-command
// snippet rendering), a "Copied!" toast flag, and the install-command map
// keyed by OS. After splitting one file per <section>, prop-drilling those
// three pieces into ~19 sections would be noise; React Context is the right
// fit.
//
// `OsTabs` reads from this context internally so callers don't have to thread
// anything through. The Getting-Started and CloudNode-Setup sections both
// render an OsTabs instance — they share a single `os` value, so flipping
// the tab in one updates the other (and the inline ``opensentry-cloudnode``
// invocation a few lines below it).
//
// Keeping this in /pages/docs/context.jsx (not /hooks/) signals that it's
// scoped to the docs route — it isn't, and shouldn't be, used elsewhere.

import { createContext, useContext, useEffect, useState } from "react"


const DocsContext = createContext(null)


export function DocsProvider({ children }) {
  // Default to linux until the userAgent sniff has run; that gives the
  // Copy buttons a sensible target on first paint without a flash of
  // "windows" content for non-Windows visitors.
  const [os, setOs] = useState("linux")
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const ua = navigator.userAgent.toLowerCase()
    if (ua.includes("win")) setOs("windows")
    else if (ua.includes("mac")) setOs("macos")
    else setOs("linux")
  }, [])

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // ``base`` resolves at module-init time on the browser, so we capture it
  // once per provider mount. Captured inside the provider rather than at
  // module top-level so test runners that stub window.location can produce
  // consistent results.
  const base = window.location.origin
  const installCommands = {
    linux: `curl -fsSL ${base}/install.sh | bash`,
    macos: `curl -fsSL ${base}/install.sh | bash`,
    windows: `irm ${base}/install.ps1 | iex`,
  }

  const value = { os, setOs, copied, copyToClipboard, base, installCommands }
  return <DocsContext.Provider value={value}>{children}</DocsContext.Provider>
}


export function useDocs() {
  const ctx = useContext(DocsContext)
  if (!ctx) {
    throw new Error("useDocs() must be used inside <DocsProvider>")
  }
  return ctx
}


// Reusable install-command tabs widget.
// Renders three OS tabs and a copy-able install command for the currently
// selected one. Two callsites today (Getting Started + CloudNode Setup) so
// the switch propagates between them via the shared `os` state.
export function OsTabs({ id }) {
  const { os, setOs, copied, copyToClipboard, installCommands } = useDocs()
  return (
    <div className="install-tabs" key={id}>
      <div className="install-tab-buttons">
        {["linux", "macos", "windows"].map((o) => (
          <button
            key={o}
            className={`install-tab-btn${os === o ? " active" : ""}`}
            onClick={() => setOs(o)}
          >
            {o === "macos" ? "macOS" : o.charAt(0).toUpperCase() + o.slice(1)}
          </button>
        ))}
      </div>
      <div className="install-tab-content">
        <div className="docs-code-block">
          <code>{installCommands[os]}</code>
          <button
            className="docs-copy-btn"
            onClick={() => copyToClipboard(installCommands[os])}
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
      </div>
    </div>
  )
}
