import { Routes, Route, Navigate } from "react-router-dom"
import { useAuth, useOrganization, CreateOrganization } from "@clerk/clerk-react"
import Layout from "./components/Layout.jsx"
import PublicLayout from "./components/PublicLayout.jsx"
import LandingPage from "./pages/LandingPage.jsx"
import DocsPage from "./pages/DocsPage.jsx"
import SignInPage from "./pages/SignInPage.jsx"
import SignUpPage from "./pages/SignUpPage.jsx"
import DashboardPage from "./pages/DashboardPage.jsx"
import SettingsPage from "./pages/SettingsPage.jsx"
import AdminPage from "./pages/AdminPage.jsx"
import TestHlsPage from "./pages/TestHlsPage.jsx"

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
    return <Navigate to="/dashboard" replace />
  }

  const isAdmin = membership?.role === "org:admin" || 
    membership?.publicUserData?.permissions?.some?.(p => 
      p === "org:admin:admin" || 
      p === "org:cameras:manage_cameras"
    )

  if (!isAdmin) {
    return <Navigate to="/dashboard" replace />
  }

  return children
}

function App() {
  return (
    <Routes>
      {/* Public routes with PublicLayout */}
      <Route element={<PublicLayout />}>
        <Route path="/" element={<LandingPage />} />
        <Route path="/docs" element={<DocsPage />} />
      </Route>

      {/* Auth routes (public but use Clerk components) */}
      <Route path="/sign-in/*" element={<SignInPage />} />
      <Route path="/sign-up/*" element={<SignUpPage />} />

      {/* Test route (public for debugging) */}
      <Route path="/test-hls" element={<TestHlsPage />} />

      {/* Authenticated routes with Layout */}
      <Route element={<Layout />}>
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
            <RequireOrg>
              <SettingsPage />
            </RequireOrg>
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
  )
}

export default App