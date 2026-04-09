import { PricingTable } from "@clerk/clerk-react"

function PricingPage() {
  return (
    <div className="pricing-page">
      <div className="pricing-glow pricing-glow-1"></div>
      <div className="pricing-glow pricing-glow-2"></div>

      <div className="pricing-hero">
        <div className="pricing-badge">PRICING</div>
        <h1 className="pricing-title">
          Security that scales<br />
          <span className="pricing-title-accent">with you</span>
        </h1>
        <p className="pricing-subtitle">
          Start free with 2 cameras. Upgrade when you need more coverage,
          team access, and admin tools.
        </p>
      </div>

      <div className="pricing-table-wrapper">
        <PricingTable for="organization" />
      </div>

      <div className="pricing-features">
        <h2 className="pricing-features-title">Every plan includes</h2>
        <div className="pricing-features-grid">
          <div className="pricing-feature-item">
            <div className="pricing-feature-icon">📡</div>
            <h3>Live Streaming</h3>
            <p>Real-time HLS video from all your cameras with low latency</p>
          </div>
          <div className="pricing-feature-item">
            <div className="pricing-feature-icon">📸</div>
            <h3>Snapshots</h3>
            <p>On-demand camera snapshots saved directly to your node</p>
          </div>
          <div className="pricing-feature-item">
            <div className="pricing-feature-icon">🔴</div>
            <h3>Recording</h3>
            <p>Start and stop recording on any camera with one click</p>
          </div>
          <div className="pricing-feature-item">
            <div className="pricing-feature-icon">🔐</div>
            <h3>End-to-End Encryption</h3>
            <p>All streams encrypted in transit with TLS and authenticated access</p>
          </div>
          <div className="pricing-feature-item">
            <div className="pricing-feature-icon">☁️</div>
            <h3>Cloud Storage</h3>
            <p>Segments stored on Tigris for reliable playback anywhere</p>
          </div>
          <div className="pricing-feature-item">
            <div className="pricing-feature-icon">🖥️</div>
            <h3>Self-Hosted Nodes</h3>
            <p>Run CloudNode on any Linux, macOS, or Windows machine</p>
          </div>
        </div>
      </div>

      <div className="pricing-faq">
        <h2 className="pricing-faq-title">Common questions</h2>
        <div className="pricing-faq-grid">
          <div className="pricing-faq-item">
            <h3>Can I upgrade or downgrade anytime?</h3>
            <p>Yes. Changes take effect immediately. If you downgrade, you keep access until the end of your billing period.</p>
          </div>
          <div className="pricing-faq-item">
            <h3>What happens if I hit my camera limit?</h3>
            <p>Your existing cameras keep working. New cameras from your node just won't be added until you upgrade or remove one.</p>
          </div>
          <div className="pricing-faq-item">
            <h3>Is the CloudNode software free?</h3>
            <p>Yes, always. CloudNode is open source and runs on your own hardware. You only pay for the Command Center cloud service.</p>
          </div>
          <div className="pricing-faq-item">
            <h3>Do you offer annual billing?</h3>
            <p>Not yet, but it's coming soon with a discount. All plans are currently billed monthly.</p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default PricingPage
