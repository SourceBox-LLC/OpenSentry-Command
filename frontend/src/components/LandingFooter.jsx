import { Link } from "react-router-dom"

function LandingFooter() {
  return (
    <footer className="landing-footer">
      <div className="landing-container">
        <div className="landing-footer-content">
          <div className="landing-footer-brand">
            <div className="landing-logo">
              <span className="landing-logo-icon">🛡️</span>
              <span>Open</span>
              <span className="landing-logo-text">Sentry</span>
            </div>
            <p>Open-source security for everyone.</p>
          </div>
          
          <div className="landing-footer-links">
            <div className="landing-footer-col">
              <h5>Product</h5>
              <Link to="/#features">Features</Link>
              <Link to="/#architecture">Architecture</Link>
              <Link to="/#quickstart">Quick Start</Link>
              <Link to="/docs">Documentation</Link>
            </div>
            
            <div className="landing-footer-col">
              <h5>Resources</h5>
              <a href="https://github.com/SourceBox-LLC/OpenSentry-Command" target="_blank" rel="noopener noreferrer">
                Command Center
              </a>
              <a href="https://github.com/SourceBox-LLC/opensentry-cloud-node" target="_blank" rel="noopener noreferrer">
                CloudNode
              </a>
              <a href="https://github.com/SourceBox-LLC" target="_blank" rel="noopener noreferrer">
                SourceBox LLC
              </a>
            </div>
            
            <div className="landing-footer-col">
              <h5>Legal</h5>
              <Link to="/legal/terms">Terms of Service</Link>
              <Link to="/legal/privacy">Privacy Policy</Link>
              <a href="https://github.com/SourceBox-LLC/OpenSentry-Command/blob/master/LICENSE" target="_blank" rel="noopener noreferrer">
                AGPL-3.0 License
              </a>
            </div>
          </div>
        </div>
        
        <div className="landing-footer-bottom">
          <p>© {new Date().getFullYear()} SourceBox LLC. Open source under AGPL-3.0.</p>
        </div>
      </div>
    </footer>
  )
}

export default LandingFooter