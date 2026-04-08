import { Outlet, Link, useLocation } from "react-router-dom"
import { SignedIn, SignedOut, UserButton, OrganizationSwitcher, useOrganization } from "@clerk/clerk-react"
import ToastContainer from "./ToastContainer.jsx"

function Layout() {
  const { organization, isLoaded: orgLoaded, membership } = useOrganization()
  const location = useLocation()

  const isAdmin = orgLoaded && membership?.role === "org:admin"

  const isActive = (path) => location.pathname === path ? "nav-link active" : "nav-link"

  return (
    <div className="layout">
      <div className="bg-grid"></div>
      <div className="bg-glow bg-glow-1"></div>
      <div className="bg-glow bg-glow-2"></div>

      <header className="header">
        <div className="header-content">
          <Link to="/" className="logo">
            <div className="logo-icon">🛡️</div>
            <div className="logo-text">Open<span>Sentry</span></div>
          </Link>

          <div className="system-status">
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
                    <Link to="/dashboard" className={isActive("/dashboard")}>
                      Dashboard
                    </Link>
                    {isAdmin && (
                      <>
                        <Link to="/settings" className={isActive("/settings")}>
                          Settings
                        </Link>
                        <Link to="/admin" className={isActive("/admin")}>
                          Admin
                        </Link>
                      </>
                    )}
                  </nav>
                </>
              )}
              <UserButton />
            </SignedIn>

            <SignedOut>
              <Link to="/sign-in" className="nav-link">
                Sign In
              </Link>
              <Link to="/sign-up" className="btn btn-primary">
                Get Started
              </Link>
            </SignedOut>
          </div>
        </div>
      </header>

      <main className="main">
        <Outlet />
      </main>

      <ToastContainer />
    </div>
  )
}

export default Layout
