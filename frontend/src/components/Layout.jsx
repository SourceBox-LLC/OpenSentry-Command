import { useEffect, useState } from "react"
import { Outlet, Link, useLocation } from "react-router-dom"
import { SignedIn, SignedOut, UserButton, OrganizationSwitcher, useOrganization } from "@clerk/clerk-react"
import { usePlanInfo } from "../hooks/usePlanInfo.jsx"
import AppSidebar from "./AppSidebar.jsx"
import ToastContainer from "./ToastContainer.jsx"
import NotificationBell from "./NotificationBell.jsx"

function Layout() {
  const { organization, isLoaded: orgLoaded } = useOrganization()
  const { planInfo } = usePlanInfo()
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const planName = planInfo?.plan || null
  const isProPlus = planName === "pro_plus"
  const isPro = planName === "pro" || isProPlus

  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") setSidebarOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  return (
    <div className="layout">
      <div className="bg-grid"></div>
      <div className="bg-glow bg-glow-1"></div>
      <div className="bg-glow bg-glow-2"></div>

      <header className="header">
        <div className="header-content">
          <div className="header-left">
            <SignedIn>
              <button
                type="button"
                className="app-sidebar-toggle"
                aria-label={sidebarOpen ? "Close navigation" : "Open navigation"}
                aria-expanded={sidebarOpen}
                onClick={() => setSidebarOpen((o) => !o)}
              >
                <span aria-hidden="true">☰</span>
              </button>
            </SignedIn>

            <Link to="/" className="logo">
              <div className="logo-icon">🛡️</div>
              <div className="logo-text">SourceBox <span>Sentry</span></div>
            </Link>
          </div>

          <div className="system-status">
            <SignedIn>
              {orgLoaded && organization && (
                <>
                  <div className="nav-org-group">
                    <OrganizationSwitcher
                      hidePersonal
                      afterCreateOrganizationUrl="/dashboard"
                      afterSelectOrganizationUrl="/dashboard"
                      createOrganizationMode="modal"
                    />
                    {isPro && (
                      <span className={`nav-plan-badge nav-plan-${isProPlus ? "pro-plus" : planName}`}>
                        {isProPlus ? "PLUS" : "PRO"}
                      </span>
                    )}
                  </div>
                  <NotificationBell />
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

      <div className="layout-body">
        <SignedIn>
          <AppSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        </SignedIn>
        <main className="main">
          <Outlet />
        </main>
      </div>

      <SignedIn>
        <div
          className="app-sidebar-backdrop"
          data-open={sidebarOpen ? "true" : "false"}
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      </SignedIn>

      <ToastContainer />
    </div>
  )
}

export default Layout
