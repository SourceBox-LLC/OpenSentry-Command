import { Outlet, Link, useLocation } from "react-router-dom"
import { SignedIn, SignedOut, UserButton, OrganizationSwitcher, useOrganization, useAuth } from "@clerk/clerk-react"
import { useState, useEffect } from "react"
import { getPlanInfo } from "../services/api"
import ToastContainer from "./ToastContainer.jsx"

function Layout() {
  const { organization, isLoaded: orgLoaded, membership } = useOrganization()
  const { getToken } = useAuth()
  const location = useLocation()
  const [planFeatures, setPlanFeatures] = useState([])

  const [planName, setPlanName] = useState(null)

  const isAdmin = orgLoaded && membership?.role === "org:admin"
  const hasAdminFeature = planFeatures.includes("admin")
  const isPro = planName === "pro" || planName === "business"

  useEffect(() => {
    if (organization && isAdmin) {
      loadPlanFeatures()
    }
  }, [organization])

  const loadPlanFeatures = async () => {
    try {
      const token = await getToken()
      const data = await getPlanInfo(() => Promise.resolve(token))
      setPlanFeatures(data.features || [])
      setPlanName(data.plan || null)
    } catch (err) {
      // Silently fail — nav still works, just hides admin link
    }
  }

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
                  <div className="nav-org-group">
                    <OrganizationSwitcher
                      hidePersonal
                      afterCreateOrganizationUrl="/dashboard"
                      afterSelectOrganizationUrl="/dashboard"
                      createOrganizationMode="modal"
                    />
                    {isPro && (
                      <span className={`nav-plan-badge nav-plan-${planName}`}>
                        {planName === "business" ? "BIZ" : "PRO"}
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
                    <Link to="/pricing" className={isActive("/pricing")}>
                      Pricing
                    </Link>
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
