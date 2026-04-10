import { useState } from "react"
import { Link } from "react-router-dom"
import { SignedIn, SignedOut, UserButton, OrganizationSwitcher, useOrganization } from "@clerk/clerk-react"

function LandingNav() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const { organization, isLoaded: orgLoaded, membership } = useOrganization()

  const isAdmin = orgLoaded && membership?.role === "org:admin"

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
            <Link to="/#features" onClick={() => setMobileMenuOpen(false)}>Features</Link>
          </li>
          <li>
            <Link to="/#architecture" onClick={() => setMobileMenuOpen(false)}>Architecture</Link>
          </li>
          <li>
            <Link to="/#quickstart" onClick={() => setMobileMenuOpen(false)}>Quick Start</Link>
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
              <>
                <OrganizationSwitcher
                  hidePersonal
                  afterCreateOrganizationUrl="/dashboard"
                  afterSelectOrganizationUrl="/dashboard"
                  createOrganizationMode="modal"
                />
                <nav className="nav-links">
                  <Link to="/dashboard" className="nav-link">
                    Dashboard
                  </Link>
                  {isAdmin && (
                    <>
                      <Link to="/settings" className="nav-link">
                        Settings
                      </Link>
                      <Link to="/admin" className="nav-link">
                        Admin
                      </Link>
                    </>
                  )}
                </nav>
              </>
            )}
            <UserButton afterSignOutUrl="/" />
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
