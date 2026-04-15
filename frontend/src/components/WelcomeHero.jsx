import { Link } from "react-router-dom"

// Dashboard empty-state heroes, differentiated by role. Admins get the
// "set up your first camera" checklist; members get a capability-focused
// welcome that tells them what they *can* do today instead of showing
// them a checklist they can't act on.
//
// Both variants share the .welcome-hero / .welcome-step CSS defined in
// index.css — no new styles needed for the split.

function CheckMarkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  )
}

export function AdminWelcomeHero() {
  return (
    <div className="welcome-hero">
      <div className="welcome-hero-header">
        <div className="welcome-hero-icon" aria-hidden="true">👋</div>
        <h2 className="welcome-hero-title">Welcome to SourceBox Sentry</h2>
        <p className="welcome-hero-subtitle">
          Your control plane is ready. SourceBox Sentry runs on your own hardware &mdash; let&rsquo;s get the first camera online.
        </p>
      </div>

      <ol className="welcome-checklist" role="list">
        <li className="welcome-step welcome-step-done">
          <span className="welcome-step-marker" aria-hidden="true">
            <CheckMarkIcon />
          </span>
          <div className="welcome-step-body">
            <div className="welcome-step-title">Workspace created</div>
            <div className="welcome-step-desc">You&rsquo;re signed in and ready to go.</div>
          </div>
        </li>

        <li className="welcome-step welcome-step-active">
          <span className="welcome-step-marker" aria-hidden="true">2</span>
          <div className="welcome-step-body">
            <div className="welcome-step-title">Install a CloudNode</div>
            <div className="welcome-step-desc">
              Run one command on any computer with a webcam. You&rsquo;ll get credentials you can paste into the setup wizard.
            </div>
            <div className="welcome-step-actions">
              <Link to="/settings" className="btn btn-primary">
                Add your first node
              </Link>
              <a
                href="https://github.com/sbussiso/opensentry-cloudnode"
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-secondary"
              >
                Installation guide ↗
              </a>
            </div>
          </div>
        </li>

        <li className="welcome-step welcome-step-pending">
          <span className="welcome-step-marker" aria-hidden="true">3</span>
          <div className="welcome-step-body">
            <div className="welcome-step-title">Camera goes live</div>
            <div className="welcome-step-desc">
              Once the node starts heartbeating, streams appear here automatically &mdash; usually within 30 seconds.
            </div>
          </div>
        </li>
      </ol>
    </div>
  )
}

export function MemberWelcomeHero({ orgName }) {
  const workspace = orgName || "this workspace"
  return (
    <div className="welcome-hero">
      <div className="welcome-hero-header">
        <div className="welcome-hero-icon" aria-hidden="true">👋</div>
        <h2 className="welcome-hero-title">
          {orgName ? `Welcome to ${orgName}` : "Welcome"}
        </h2>
        <p className="welcome-hero-subtitle">
          You&rsquo;ve joined as a member. Live camera feeds will appear here as an admin adds them &mdash; no setup on your end.
        </p>
      </div>

      <ol className="welcome-checklist" role="list">
        <li className="welcome-step welcome-step-done">
          <span className="welcome-step-marker" aria-hidden="true">
            <CheckMarkIcon />
          </span>
          <div className="welcome-step-body">
            <div className="welcome-step-title">Live monitoring</div>
            <div className="welcome-step-desc">
              Camera feeds appear on this page and auto-refresh every 5 seconds as they come online.
            </div>
          </div>
        </li>

        <li className="welcome-step welcome-step-done">
          <span className="welcome-step-marker" aria-hidden="true">
            <CheckMarkIcon />
          </span>
          <div className="welcome-step-body">
            <div className="welcome-step-title">Real-time motion alerts</div>
            <div className="welcome-step-desc">
              When a camera detects motion, you&rsquo;ll get a notification in the bell icon at the top right.
            </div>
          </div>
        </li>

        <li className="welcome-step welcome-step-done">
          <span className="welcome-step-marker" aria-hidden="true">
            <CheckMarkIcon />
          </span>
          <div className="welcome-step-body">
            <div className="welcome-step-title">Team workspace</div>
            <div className="welcome-step-desc">
              You&rsquo;re collaborating securely in {workspace}. An admin manages cameras and access; you focus on watching.
            </div>
          </div>
        </li>
      </ol>

      <div className="welcome-hero-footnote">
        Need admin access? Ask a workspace admin to promote you from the Settings page.
      </div>
    </div>
  )
}
