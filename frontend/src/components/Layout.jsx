import { Outlet, Link } from "react-router-dom"
import { SignedIn, SignedOut, UserButton, OrganizationSwitcher, useOrganization, useAuth } from "@clerk/clerk-react"
import ToastContainer from "./ToastContainer.jsx"

const DashboardIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="7"/>
    <rect x="14" y="3" width="7" height="7"/>
    <rect x="14" y="14" width="7" height="7"/>
    <rect x="3" y="14" width="7" height="7"/>
  </svg>
)

const MediaIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
    <circle cx="8.5" cy="8.5" r="1.5"/>
    <polyline points="21 15 16 10 5 21"/>
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

function Layout() {
  const { organization, isLoaded: orgLoaded, membership } = useOrganization()
  const { isSignedIn } = useAuth()

  const isAdmin = membership?.role === "org:admin" || 
    membership?.publicUserData?.permissions?.some?.(p => 
      p === "org:admin:admin" || 
      p === "org:cameras:manage_cameras"
    )

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
                <OrganizationSwitcher
                  hidePersonal
                  afterCreateOrganizationUrl="/dashboard"
                  afterSelectOrganizationUrl="/dashboard"
                  createOrganizationMode="modal"
                />
              )}
              <UserButton>
                <UserButton.MenuItems>
                  <UserButton.Link
                    label="Dashboard"
                    labelIcon={<DashboardIcon />}
                    href="/dashboard"
                  />
                  <UserButton.Link
                    label="Media"
                    labelIcon={<MediaIcon />}
                    href="/media"
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