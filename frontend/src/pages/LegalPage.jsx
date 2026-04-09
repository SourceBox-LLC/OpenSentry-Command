import { useParams, Link } from "react-router-dom"

const LAST_UPDATED = "April 9, 2026"

function TermsContent() {
  return (
    <>
      <h1>Terms of Service</h1>
      <p className="legal-updated">Last updated: {LAST_UPDATED}</p>

      <h2>1. Acceptance of Terms</h2>
      <p>
        By accessing or using the OpenSentry Command Center service ("Service"),
        you agree to be bound by these Terms of Service. If you are using the
        Service on behalf of an organization, you represent that you have
        authority to bind that organization to these terms.
      </p>

      <h2>2. Description of Service</h2>
      <p>
        OpenSentry provides a cloud-hosted security camera management platform
        that enables users to connect local camera nodes, view live video
        streams, and manage camera configurations. The Service includes web
        dashboard access, API access, and MCP (Model Context Protocol)
        integration for AI-powered camera interaction.
      </p>

      <h2>3. Accounts and Organizations</h2>
      <p>
        You must create an account and organization to use the Service.
        You are responsible for maintaining the confidentiality of your account
        credentials and API keys. You must notify us immediately of any
        unauthorized use of your account.
      </p>

      <h2>4. Subscription Plans and Payment</h2>
      <p>
        The Service offers Free, Pro, and Business subscription tiers. Paid
        plans are billed monthly. Upgrades take effect immediately; downgrades
        take effect at the end of the current billing period. You retain access
        to paid features until the end of your billing cycle after cancellation.
      </p>
      <p>
        If a payment fails, your account will enter a grace period during which
        we will retry the charge. If payment cannot be collected, your account
        may be downgraded to the Free plan.
      </p>

      <h2>5. Acceptable Use</h2>
      <p>You agree not to:</p>
      <ul>
        <li>Use the Service for any unlawful purpose or in violation of any applicable laws</li>
        <li>Attempt to gain unauthorized access to the Service or its related systems</li>
        <li>Interfere with or disrupt the Service or its infrastructure</li>
        <li>Use the Service to store or transmit malicious code</li>
        <li>Reverse engineer, decompile, or disassemble the Service</li>
        <li>Resell or redistribute access to the Service without authorization</li>
      </ul>

      <h2>6. API Keys and Access Credentials</h2>
      <p>
        API keys (including CloudNode keys and MCP API keys) are sensitive
        credentials. You are solely responsible for securing your keys. We
        store keys using SHA-256 hashing and never retain plaintext copies.
        If you believe a key has been compromised, revoke it immediately
        through the dashboard.
      </p>

      <h2>7. Data and Video Content</h2>
      <p>
        You retain ownership of all video content captured by your cameras and
        stored through the Service. We do not access, view, or share your
        video content except as necessary to provide the Service or as required
        by law. Video segments are stored in your organization's isolated
        storage namespace.
      </p>

      <h2>8. Service Availability</h2>
      <p>
        We strive to maintain high availability but do not guarantee
        uninterrupted service. The Service is provided "as is" without
        warranties of any kind. We are not liable for any losses resulting
        from service interruptions, data loss, or security breaches.
      </p>

      <h2>9. Limitation of Liability</h2>
      <p>
        To the maximum extent permitted by law, OpenSentry and its operators
        shall not be liable for any indirect, incidental, special,
        consequential, or punitive damages, or any loss of profits or
        revenues, whether incurred directly or indirectly.
      </p>

      <h2>10. Termination</h2>
      <p>
        Either party may terminate the agreement at any time. Upon
        termination, your access to the Service will cease and your data
        may be deleted after a reasonable retention period. You may use the
        Full Reset feature in the Danger Zone to delete all your data
        before canceling.
      </p>

      <h2>11. Changes to Terms</h2>
      <p>
        We may update these Terms of Service from time to time. Material
        changes will be communicated through the Service dashboard. Your
        continued use of the Service after changes constitutes acceptance
        of the updated terms.
      </p>

      <h2>12. Governing Law</h2>
      <p>
        These Terms shall be governed by and construed in accordance with
        the laws of the United States, without regard to conflict of law
        provisions.
      </p>

      <h2>13. Contact</h2>
      <p>
        For questions about these Terms, please open an issue on our{" "}
        <a href="https://github.com/SourceBox-LLC/OpenSentry-Command/issues" target="_blank" rel="noopener noreferrer">
          GitHub repository
        </a>{" "}
        or contact the project maintainers.
      </p>
    </>
  )
}

function PrivacyContent() {
  return (
    <>
      <h1>Privacy Policy</h1>
      <p className="legal-updated">Last updated: {LAST_UPDATED}</p>

      <h2>1. Information We Collect</h2>

      <h3>Account Information</h3>
      <p>
        When you create an account, we collect your name, email address, and
        organization details through our authentication provider (Clerk).
        We do not store passwords directly.
      </p>

      <h3>Camera and Video Data</h3>
      <p>
        Video segments captured by your CloudNode cameras are uploaded to
        cloud storage (Tigris/S3) under your organization's isolated namespace.
        We do not access, analyze, or share your video content. Video segments
        are automatically cleaned up based on your retention settings.
      </p>

      <h3>Usage and Log Data</h3>
      <p>We collect operational data to provide and improve the Service:</p>
      <ul>
        <li>Stream access logs (who viewed which camera, when, IP address)</li>
        <li>MCP tool call activity (tool name, API key used, timestamps)</li>
        <li>Node registration and heartbeat data (hostname, local IP, camera status)</li>
        <li>Audit logs for administrative actions</li>
      </ul>
      <p>
        All log data is automatically deleted after 90 days (configurable by
        the operator).
      </p>

      <h3>Codec and Device Information</h3>
      <p>
        Your CloudNode reports video/audio codec information (e.g.,
        H.264 profile, AAC format) to ensure proper HLS stream playback.
        No other device information is collected.
      </p>

      <h2>2. How We Use Your Information</h2>
      <p>We use collected information to:</p>
      <ul>
        <li>Provide, maintain, and improve the Service</li>
        <li>Authenticate users and enforce organization-based access control</li>
        <li>Serve HLS video streams with correct codec parameters</li>
        <li>Enforce plan limits (cameras, nodes, MCP rate limits)</li>
        <li>Generate usage statistics visible in your admin dashboard</li>
        <li>Detect and prevent abuse or unauthorized access</li>
      </ul>

      <h2>3. Data Storage and Security</h2>
      <ul>
        <li>All API keys are stored as SHA-256 hashes; plaintext keys are never retained</li>
        <li>Video data is stored in isolated cloud storage namespaces per organization</li>
        <li>All connections use HTTPS with HSTS enforcement</li>
        <li>Authentication is handled by Clerk with industry-standard JWT verification</li>
        <li>Organization data is isolated at the database level using org_id scoping</li>
      </ul>

      <h2>4. Data Sharing</h2>
      <p>We do not sell, rent, or share your personal information or video data with third parties except:</p>
      <ul>
        <li><strong>Service providers:</strong> Clerk (authentication), Tigris (video storage), Fly.io (hosting)</li>
        <li><strong>Legal requirements:</strong> When required by law, regulation, or legal process</li>
        <li><strong>Safety:</strong> To protect the rights, property, or safety of our users or the public</li>
      </ul>

      <h2>5. Data Retention</h2>
      <ul>
        <li>Video segments are retained based on your configured retention settings (default: last 60 segments per camera)</li>
        <li>Stream access logs, MCP activity logs, and audit logs are retained for 90 days, then automatically deleted</li>
        <li>Account data is retained as long as your account is active</li>
        <li>You can delete all your data at any time using the Danger Zone &gt; Full Reset feature</li>
      </ul>

      <h2>6. Your Rights</h2>
      <p>You have the right to:</p>
      <ul>
        <li><strong>Access:</strong> View your data through the dashboard and admin panel</li>
        <li><strong>Deletion:</strong> Delete all your organization data via Full Reset in the Danger Zone</li>
        <li><strong>Portability:</strong> Stream access logs and MCP activity are viewable in the admin dashboard</li>
        <li><strong>Objection:</strong> You may cancel your account at any time</li>
      </ul>

      <h2>7. Cookies</h2>
      <p>
        We use cookies only for authentication session management through
        Clerk. We do not use advertising or tracking cookies. No cookie
        consent banner is required as our cookies are strictly necessary
        for the Service to function.
      </p>

      <h2>8. Children's Privacy</h2>
      <p>
        The Service is not intended for use by individuals under the age
        of 18. We do not knowingly collect information from children.
      </p>

      <h2>9. Changes to This Policy</h2>
      <p>
        We may update this Privacy Policy from time to time. Material changes
        will be communicated through the Service dashboard. Your continued use
        of the Service after changes constitutes acceptance.
      </p>

      <h2>10. Contact</h2>
      <p>
        For privacy-related questions, please open an issue on our{" "}
        <a href="https://github.com/SourceBox-LLC/OpenSentry-Command/issues" target="_blank" rel="noopener noreferrer">
          GitHub repository
        </a>{" "}
        or contact the project maintainers.
      </p>
    </>
  )
}

function LegalPage() {
  const { page } = useParams()

  return (
    <div className="legal-container">
      <div className="legal-nav">
        <Link to="/legal/terms" className={page === "terms" ? "active" : ""}>Terms of Service</Link>
        <Link to="/legal/privacy" className={page === "privacy" ? "active" : ""}>Privacy Policy</Link>
      </div>
      <div className="legal-content">
        {page === "privacy" ? <PrivacyContent /> : <TermsContent />}
      </div>
    </div>
  )
}

export default LegalPage
