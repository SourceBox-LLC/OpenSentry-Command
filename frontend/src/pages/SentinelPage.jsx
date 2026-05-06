import { Link } from "react-router-dom"
import {
  EyeIcon,
  BrainIcon,
  FileTextIcon,
  CrosshairIcon,
  LinkIcon,
  ShieldCheckIcon,
} from "../components/FeatureIcons.jsx"

function SentinelPage() {
  return (
    <div className="sentinel-page">
      <div className="sentinel-glow sentinel-glow-1"></div>
      <div className="sentinel-glow sentinel-glow-2"></div>

      <div className="sentinel-hero">
        <div className="sentinel-badge-row">
          <span className="sentinel-badge">SENTINEL</span>
          <span className="sentinel-soon-pill">COMING SOON</span>
        </div>
        <h1 className="sentinel-title">
          Your autonomous<br />
          <span className="sentinel-title-accent">AI security agent</span>
        </h1>
        <p className="sentinel-subtitle">
          Sentinel is a purpose-built AI agent wired directly into your
          SourceBox Sentry MCP server. The moment motion is detected, Sentinel
          investigates, reasons about what it sees, and writes a full
          incident report — no human required.
        </p>
      </div>

      <div className="sentinel-banner" aria-hidden="true">
        <picture>
          <source srcSet="/images/sentinel-hero.webp" type="image/webp" />
          <img
            src="/images/sentinel-hero.jpg"
            alt=""
            className="sentinel-banner-image"
            width="2240"
            height="960"
            loading="lazy"
          />
        </picture>
        <div className="sentinel-banner-caption">
          What Sentinel sees, at 3am, when motion fires.
        </div>
      </div>

      <div className="sentinel-status-card">
        <div className="sentinel-status-row">
          <div className="sentinel-status-dot"></div>
          <div className="sentinel-status-text">
            <strong>In development.</strong> We're building a model trained
            specifically for this job. Until then, you can connect any
            MCP-capable agent — like Claude Desktop — to your Command Center
            and get equivalent capabilities today.
          </div>
        </div>
        <Link to="/mcp" className="sentinel-status-link">
          Use the MCP now →
        </Link>
      </div>

      <div className="sentinel-features">
        <h2 className="sentinel-features-title">What Sentinel will do</h2>
        <div className="sentinel-features-grid">
          <div className="sentinel-feature-item">
            <div className="sentinel-feature-icon"><EyeIcon /></div>
            <h3>Motion-triggered response</h3>
            <p>
              Wakes up the instant a camera reports motion. No polling,
              no missed events — subscribes to the MCP motion stream directly.
            </p>
          </div>
          <div className="sentinel-feature-item">
            <div className="sentinel-feature-icon"><BrainIcon /></div>
            <h3>Visual reasoning</h3>
            <p>
              Pulls a live snapshot, analyzes the scene, and decides what it's
              looking at — intruder, pet, delivery, false alarm.
            </p>
          </div>
          <div className="sentinel-feature-item">
            <div className="sentinel-feature-icon"><FileTextIcon /></div>
            <h3>Automatic incident reports</h3>
            <p>
              Generates a structured report with evidence — snapshot, short
              clip, written observation — and files it to your inbox.
            </p>
          </div>
          <div className="sentinel-feature-item">
            <div className="sentinel-feature-icon"><CrosshairIcon /></div>
            <h3>Trained for surveillance</h3>
            <p>
              Unlike a general-purpose LLM, Sentinel is tuned on security
              footage — better at distinguishing real threats from noise.
            </p>
          </div>
          <div className="sentinel-feature-item">
            <div className="sentinel-feature-icon"><LinkIcon /></div>
            <h3>Native MCP integration</h3>
            <p>
              Built on the same Model Context Protocol server your other
              agents use — all 17 tools available, zero config.
            </p>
          </div>
          <div className="sentinel-feature-item">
            <div className="sentinel-feature-icon"><ShieldCheckIcon /></div>
            <h3>Stays in your org</h3>
            <p>
              Scoped to your organization's cameras and data. Never sees
              other tenants. Same isolation guarantees as the rest of the
              platform.
            </p>
          </div>
        </div>
      </div>

      <div className="sentinel-roadmap">
        <h2 className="sentinel-roadmap-title">Until Sentinel ships</h2>
        <p className="sentinel-roadmap-text">
          You can use any MCP-capable agent today. Claude Desktop, Cursor,
          and other agent providers can connect directly to your Command
          Center with an API key from the MCP page. Same tools, same motion
          alerts, same incident reporting — driven by the agent of your
          choice.
        </p>
        <div className="sentinel-roadmap-actions">
          <Link to="/mcp" className="sentinel-cta sentinel-cta-primary">
            Connect an agent
          </Link>
          <Link to="/docs" className="sentinel-cta sentinel-cta-ghost">
            Read the docs
          </Link>
        </div>
      </div>
    </div>
  )
}

export default SentinelPage
