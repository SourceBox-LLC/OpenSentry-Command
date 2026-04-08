import { useState } from "react"
import { Link } from "react-router-dom"
import { SignedIn, SignedOut, UserButton, OrganizationSwitcher, useOrganization } from "@clerk/clerk-react"

const DashboardIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="7"/>
    <rect x="14" y="3" width="7" height="7"/>
    <rect x="14" y="14" width="7" height="7"/>
    <rect x="3" y="14" width="7" height="7"/>
  </svg>
)

const SettingsIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
  </svg>
)

const AdminIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
  </svg>
)

function LandingNav() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const { organization, isLoaded: orgLoaded, membership } = useOrganization()

  const isAdmin = membership?.role === "org:admin" ||
    membership?.publicUserData?.permissions?.some?.(p =>
      p === "org:admin:admin" ||
      p === "org:cameras:manage_cameras"
    )

  return (
    <nav className="landing-nav">
      <div className="landing-nav-container">
        <Link to="/" className="landing-logo">
          <span className="landing-logo-icon">🛡️</span>
          <span>Open</span>
          <span className="landing-logo-text">Sentry</span>
        </Link>

        <ul className={`landing-nav-links ${mobileMenuOpen ? 'active' : ''}`}>
          <li>
            <a href="/#features" onClick={() => setMobileMenuOpen(false)}>Features</a>
          </li>
          <li>
            <a href="/#architecture" onClick={() => setMobileMenuOpen(false)}>Architecture</a>
          </li>
          <li>
            <a href="/#quickstart" onClick={() => setMobileMenuOpen(false)}>Quick Start</a>
          </li>
          <li>
            <Link to="/docs" onClick={() => setMobileMenuOpen(false)}>Docs</Link>
          </li>
        </ul>

        <div className="landing-nav-actions">
          <SignedOut>
            <Link to="/sign-in" className="landing-btn landing-btn-ghost">
              Sign In
            </Link>
            <Link to="/sign-up" className="landing-btn landing-btn-primary">
              Get Started
            </Link>
          </SignedOut>

          <SignedIn>
            {orgLoaded && organization && (
              <OrganizationSwitcher
                hidePersonal
                afterCreateOrganizationUrl="/dashboard"
                afterSelectOrganizationUrl="/dashboard"
                createOrganizationMode="modal"
              />
            )}
            <UserButton afterSignOutUrl="/">
              <UserButton.MenuItems>
                <UserButton.Link
                  label="Dashboard"
                  labelIcon={<DashboardIcon />}
                  href="/dashboard"
                />
                <UserButton.Link
                  label="Settings"
                  labelIcon={<SettingsIcon />}
                  href="/settings"
                />
                {isAdmin && (
                  <UserButton.Link
                    label="Admin"
                    labelIcon={<AdminIcon />}
                    href="/admin"
                  />
                )}
              </UserButton.MenuItems>
            </UserButton>
          </SignedIn>
        </div>

        <button
          className="landing-mobile-menu-btn"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="Toggle menu"
        >
          <span></span>
          <span></span>
          <span></span>
        </button>
      </div>
    </nav>
  )
}

export default LandingNav