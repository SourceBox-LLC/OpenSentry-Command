import { Link } from "react-router-dom"

import { DocsProvider } from "./docs/context"

// One file per <section>. Each component is self-contained — sections that
// need shared state (the OS-tabs choice, the Copy-button toast) pull it from
// useDocs() rather than props. See pages/docs/context.jsx for the provider.
import GettingStarted from "./docs/GettingStarted"
import CloudNodeSetup from "./docs/CloudNodeSetup"
import Configuration from "./docs/Configuration"
import Deployment from "./docs/Deployment"
import MotionDetection from "./docs/MotionDetection"
import TerminalDashboard from "./docs/TerminalDashboard"
import Dashboard from "./docs/Dashboard"
import Recording from "./docs/Recording"
import CameraGroups from "./docs/CameraGroups"
import Notifications from "./docs/Notifications"
import Mcp from "./docs/Mcp"
import Plans from "./docs/Plans"
import Architecture from "./docs/Architecture"
import SecurityProcedures from "./docs/SecurityProcedures"
import Troubleshooting from "./docs/Troubleshooting"
import Faq from "./docs/Faq"
import ApiReference from "./docs/ApiReference"
import ApiRateLimits from "./docs/ApiRateLimits"
import Resources from "./docs/Resources"


function DocsSidebar() {
  return (
    <aside className="docs-sidebar">
      <div className="docs-sidebar-header">
        <h2>SourceBox Sentry</h2>
        <p>Documentation</p>
      </div>
      <nav className="docs-sidebar-nav">
        <div className="docs-sidebar-group">
          <div className="docs-sidebar-group-label">Introduction</div>
          <a href="#getting-started" className="docs-sidebar-link">Getting Started</a>
          <a href="#architecture" className="docs-sidebar-link">Architecture</a>
        </div>
        <div className="docs-sidebar-group">
          <div className="docs-sidebar-group-label">CloudNode</div>
          <a href="#cloudnode-setup" className="docs-sidebar-link">Setup</a>
          <a href="#configuration" className="docs-sidebar-link">Configuration</a>
          <a href="#deployment" className="docs-sidebar-link">Deployment</a>
          <a href="#motion-detection" className="docs-sidebar-link">Motion Detection</a>
          <a href="#terminal-dashboard" className="docs-sidebar-link">Terminal Dashboard</a>
        </div>
        <div className="docs-sidebar-group">
          <div className="docs-sidebar-group-label">Command Center</div>
          <a href="#dashboard" className="docs-sidebar-link">Dashboard & Features</a>
          <a href="#recording" className="docs-sidebar-link">Recording & Retention</a>
          <a href="#camera-groups" className="docs-sidebar-link">Camera Groups</a>
          <a href="#notifications" className="docs-sidebar-link">Notifications</a>
        </div>
        <div className="docs-sidebar-group">
          <div className="docs-sidebar-group-label">Integrations</div>
          <a href="#mcp" className="docs-sidebar-link">MCP Integration</a>
        </div>
        <div className="docs-sidebar-group">
          <div className="docs-sidebar-group-label">Account & Security</div>
          <a href="#plans" className="docs-sidebar-link">Plans & Limits</a>
          <a href="#security-procedures" className="docs-sidebar-link">Security Procedures</a>
        </div>
        <div className="docs-sidebar-group">
          <div className="docs-sidebar-group-label">Help</div>
          <a href="#troubleshooting" className="docs-sidebar-link">Troubleshooting</a>
          <a href="#faq" className="docs-sidebar-link">FAQ</a>
        </div>
        <div className="docs-sidebar-group">
          <div className="docs-sidebar-group-label">Reference</div>
          <a href="#api-reference" className="docs-sidebar-link">API Reference</a>
          <a href="#api-rate-limits" className="docs-sidebar-link">API Rate Limits</a>
        </div>
      </nav>
      <div className="docs-sidebar-footer">
        <Link to="/sign-up" className="docs-sidebar-btn">
          Get Started Free
        </Link>
      </div>
    </aside>
  )
}


function DocsPage() {
  return (
    <DocsProvider>
      <div className="docs-layout">
        <DocsSidebar />
        <main className="docs-content">
          <div className="docs-content-inner">
            <div className="docs-header">
              <h1>Documentation</h1>
              <p>Complete guides for deploying, using, and integrating with SourceBox Sentry.</p>
            </div>

            <GettingStarted />
            <CloudNodeSetup />
            <Configuration />
            <Deployment />
            <MotionDetection />
            <TerminalDashboard />
            <Dashboard />
            <Recording />
            <CameraGroups />
            <Notifications />
            <Mcp />
            <Plans />
            <Architecture />
            <SecurityProcedures />
            <Troubleshooting />
            <Faq />
            <ApiReference />
            <ApiRateLimits />
            <Resources />

            <div className="docs-cta">
              <p>Ready to set up your security camera system?</p>
              <Link to="/sign-up" className="docs-cta-btn">Create Free Account</Link>
            </div>
          </div>
        </main>
      </div>
    </DocsProvider>
  )
}

export default DocsPage
