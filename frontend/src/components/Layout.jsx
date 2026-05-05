import { Outlet, Link, useLocation } from "react-router-dom"
import { SignedIn, SignedOut, UserButton, OrganizationSwitcher, useOrganization } from "@clerk/clerk-react"
import { usePlanInfo } from "../hooks/usePlanInfo.jsx"
import ToastContainer from "./ToastContainer.jsx"
import NotificationBell from "./NotificationBell.jsx"

function Layout() {
  const { organization, isLoaded: orgLoaded, membership } = useOrganization()
  const { planInfo } = usePlanInfo()
  const location = useLocation()

  const isAdmin = orgLoaded && membership?.role === "org:admin"
  const planFeatures = planInfo?.features || []
  const planName = planInfo?.plan || null
  const hasAdminFeature = planFeatures.includes("admin")
  // ``business`` is the pre-rename Clerk slug, still valid as a transitional
  // alias in the backend — accept it here so users with a stale JWT still see
  // their paid badge while the token refreshes.
  const isProPlus = planName === "pro_plus" || planName === "business"
  const isPro = planName === "pro" || isProPlus

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
            <div className="logo-text">SourceBox <span>Sentry</span></div>
          </Link>

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
                  <nav className="nav-links">
                    <Link to="/dashboard" className={isActive("/dashboard")}>
                      Dashboard
                    </Link>
                    {isAdmin && (
                      <>
                        <Link to="/settings" className={isActive("/settings")}>
                          Settings
                        </Link>
                        {hasAdminFeature ? (
                          <Link to="/admin" className={isActive("/admin")}>
                            Admin
                          </Link>
                        ) : (
                          <Link to="/admin" className={`${isActive("/admin")} nav-link-locked`}>
                            Admin
                            <span className="nav-pro-badge">PRO</span>
                          </Link>
                        )}
                      </>
                    )}
                    <Link to="/mcp" className={isActive("/mcp")}>
                      MCP
                    </Link>
                    <Link to="/sentinel" className={isActive("/sentinel")}>
                      Sentinel
                      <span className="nav-soon-badge">SOON</span>
                    </Link>
                    {/*
                      Help → /docs.  Sits between the product nav and the
                      "supporting" cluster (Pricing) intentionally — users
                      hunting for "where do I find...?" scan the right side
                      of the nav, and Help next to Pricing matches every
                      SaaS convention they've already internalised.

                      Support email is intentionally NOT here yet —
                      support.sourceboxsentry.com is unprovisioned and a
                      mailto: link to a non-existent address would
                      bounce silently.  Add when the domain lands.
                    */}
                    <Link to="/docs" className={isActive("/docs")}>
                      Help
                    </Link>
                    <Link to="/pricing" className={isActive("/pricing")}>
                      Pricing
                    </Link>
                  </nav>
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

      <main className="main">
        <Outlet />
      </main>

      <ToastContainer />
    </div>
  )
}

export default Layout
