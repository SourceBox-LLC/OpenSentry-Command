import { lazy, Suspense } from "react"
import { Routes, Route, Navigate } from "react-router-dom"
import { useAuth, useOrganization, CreateOrganization } from "@clerk/clerk-react"
import Layout from "./components/Layout.jsx"
import PublicLayout from "./components/PublicLayout.jsx"
import LoadingSpinner from "./components/LoadingSpinner.jsx"

// Lazy-load pages to reduce initial bundle size
const LandingPage = lazy(() => import("./pages/LandingPage.jsx"))
const DocsPage = lazy(() => import("./pages/DocsPage.jsx"))
const SignInPage = lazy(() => import("./pages/SignInPage.jsx"))
const SignUpPage = lazy(() => import("./pages/SignUpPage.jsx"))
const DashboardPage = lazy(() => import("./pages/DashboardPage.jsx"))
const SettingsPage = lazy(() => import("./pages/SettingsPage.jsx"))
const AdminPage = lazy(() => import("./pages/AdminPage.jsx"))
const TestHlsPage = lazy(() => import("./pages/TestHlsPage.jsx"))
const PricingPage = lazy(() => import("./pages/PricingPage.jsx"))

function RequireOrg({ children }) {
  const { organization, isLoaded } = useOrganization()
  const { isSignedIn } = useAuth()

  if (!isLoaded) {
    return (
      <div className="loading-container">
        <div className="loading-spinner"></div>
      </div>
    )
  }

  if (!isSignedIn) {
    return <Navigate to="/sign-in" replace />
  }

  if (!organization) {
    return (
      <div className="org-creation-page">
        <div className="org-creation-card">
          <div className="org-creation-icon">🏢</div>
          <h1 className="org-creation-title">Create Your Organization</h1>
          <p className="org-creation-subtitle">
            Organizations help you manage cameras and collaborate with your team.
            You can invite members and control permissions.
          </p>
          <div className="org-creation-form">
            <CreateOrganization afterCreateOrganizationUrl="/dashboard" />
          </div>
        </div>
      </div>
    )
  }

  return children
}

function RequireAdmin({ children }) {
  const { organization, membership, isLoaded } = useOrganization()
  const { isSignedIn, has } = useAuth()

  if (!isLoaded) {
    return (
      <div className="loading-container">
        <div className="loading-spinner"></div>
      </div>
    )
  }

  if (!isSignedIn) {
    return <Navigate to="/sign-in" replace />
  }

  if (!organization) {
    return <Navigate to="/dashboard" replace />
  }

  const isAdmin = has?.({ role: "org:admin" }) ||
    membership?.role === "org:admin" ||
    membership?.role === "admin"

  if (!isAdmin) {
    return <Navigate to="/dashboard" replace />
  }

  return children
}

function App() {
  return (
    <Suspense fallback={<div className="loading-container"><LoadingSpinner /></div>}>
      <Routes>
        {/* Public routes with PublicLayout */}
        <Route element={<PublicLayout />}>
          <Route path="/" element={<LandingPage />} />
          <Route path="/docs" element={<DocsPage />} />
        </Route>

        {/* Auth routes (public but use Clerk components) */}
        <Route path="/sign-in/*" element={<SignInPage />} />
        <Route path="/sign-up/*" element={<SignUpPage />} />

        {/* Test route (admin only) */}
        <Route element={<Layout />}>
          <Route
            path="/test-hls"
            element={
              <RequireAdmin>
                <TestHlsPage />
              </RequireAdmin>
            }
          />
        </Route>

        {/* Authenticated routes with Layout */}
        <Route element={<Layout />}>
          <Route
            path="/pricing"
            element={
              <RequireOrg>
                <PricingPage />
              </RequireOrg>
            }
          />
          <Route
            path="/dashboard"
            element={
              <RequireOrg>
                <DashboardPage />
              </RequireOrg>
            }
          />
          <Route
            path="/settings"
            element={
              <RequireAdmin>
                <SettingsPage />
              </RequireAdmin>
            }
          />
          <Route
            path="/admin"
            element={
              <RequireAdmin>
                <AdminPage />
              </RequireAdmin>
            }
          />
        </Route>
      </Routes>
    </Suspense>
  )
}

export default App