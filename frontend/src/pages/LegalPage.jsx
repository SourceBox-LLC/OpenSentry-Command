import { useParams, Link } from "react-router-dom"

const LAST_UPDATED = "April 9, 2026"
const CONTACT_EMAIL = "legal@sourcebox.dev"

function TermsContent() {
  return (
    <>
      <h1>Terms of Service</h1>
      <p className="legal-updated">Last updated: {LAST_UPDATED}</p>

      <h2>1. Acceptance of Terms</h2>
      <p>
        By accessing or using the SourceBox Sentry Command Center service ("Service"),
        operated by SourceBox LLC ("Company," "we," "us," or "our"),
        you ("User," "you," or "your") agree to be bound by these Terms of
        Service ("Terms"). If you are using the Service on behalf of an
        organization, you represent and warrant that you have authority to
        bind that organization to these Terms, and "you" refers to both you
        individually and the organization.
      </p>
      <p>
        If you do not agree to these Terms, you must not access or use the
        Service.
      </p>

      <h2>2. Description of Service</h2>
      <p>
        SourceBox Sentry provides a cloud-hosted security camera management platform
        that enables users to connect local camera nodes, view live video
        streams, and manage camera configurations. The Service includes web
        dashboard access, API access, and MCP (Model Context Protocol)
        integration for AI-powered camera interaction.
      </p>

      <h2>3. Important Security Camera Disclaimer</h2>
      <p>
        <strong>
          THE SERVICE IS A CAMERA MANAGEMENT AND VIEWING TOOL ONLY. IT IS
          NOT A PROFESSIONAL SECURITY, SURVEILLANCE, OR ALARM MONITORING
          SYSTEM AND SHOULD NOT BE RELIED UPON AS SUCH.
        </strong>
      </p>
      <p>
        The Service does not provide emergency response, law enforcement
        notification, or 24/7 monitoring. We do not guarantee that cameras
        will remain online, that video will be captured or retained during
        any specific event, or that the Service will detect, prevent, or
        record any incident including but not limited to theft, vandalism,
        trespass, or personal injury.
      </p>
      <p>
        You acknowledge that camera connectivity depends on your local
        network, hardware, power supply, and internet connection, none of
        which are under our control. You are solely responsible for your
        own physical security arrangements.
      </p>

      <h2>4. Compliance with Surveillance and Recording Laws</h2>
      <p>
        You are solely responsible for ensuring that your use of the Service
        complies with all applicable federal, state, local, and international
        laws and regulations regarding video surveillance, audio recording,
        data collection, and privacy, including but not limited to:
      </p>
      <ul>
        <li>Consent requirements for audio and video recording in your jurisdiction</li>
        <li>Signage or notice requirements for surveillance in your area</li>
        <li>Restrictions on recording in private spaces or workplaces</li>
        <li>Data protection regulations (such as GDPR, CCPA, or equivalent local laws)</li>
      </ul>
      <p>
        We do not provide legal advice regarding surveillance compliance.
        You should consult with a qualified attorney to understand your
        obligations. We are not liable for any claims, fines, or damages
        arising from your failure to comply with applicable surveillance
        or recording laws.
      </p>

      <h2>5. Accounts and Organizations</h2>
      <p>
        You must create an account and organization to use the Service.
        You are responsible for maintaining the confidentiality of your
        account credentials and all API keys (including CloudNode keys and
        MCP keys). You must notify us immediately of any unauthorized use
        of your account. You are responsible for all activity that occurs
        under your account.
      </p>

      <h2>6. Subscription Plans and Payment</h2>
      <p>
        The Service offers Free, Pro, and Business subscription tiers. Paid
        plans are billed monthly through our payment processor. Upgrades
        take effect immediately; downgrades take effect at the end of the
        current billing period. You retain access to paid features until the
        end of your billing cycle after cancellation.
      </p>
      <p>
        If a payment fails, your account will enter a grace period during
        which the charge will be retried. During this period, your ability
        to create new resources (nodes, API keys) will be restricted. If
        payment cannot be collected, your account may be downgraded to the
        Free plan and resources exceeding Free plan limits may become
        inaccessible.
      </p>

      <h2>7. Acceptable Use</h2>
      <p>You agree not to:</p>
      <ul>
        <li>Use the Service for any unlawful purpose or in violation of any applicable laws</li>
        <li>Use the Service to conduct surveillance in violation of any person's reasonable expectation of privacy</li>
        <li>Attempt to gain unauthorized access to the Service or its related systems</li>
        <li>Interfere with or disrupt the Service or its infrastructure</li>
        <li>Use the Service to store or transmit malicious code</li>
        <li>Reverse engineer, decompile, or disassemble the Service</li>
        <li>Resell or redistribute access to the Service without authorization</li>
        <li>Exceed published rate limits or abuse API access</li>
      </ul>

      <h2>8. API Keys and Access Credentials</h2>
      <p>
        API keys (including CloudNode keys and MCP API keys) are sensitive
        credentials. You are solely responsible for securing your keys and
        for any actions taken using them. We store keys using SHA-256 hashing
        and never retain plaintext copies. If you believe a key has been
        compromised, you must revoke it immediately through the dashboard.
      </p>

      <h2>9. Data and Video Content</h2>
      <p>
        You retain ownership of all video content captured by your cameras and
        served through the Service. We do not access, view, or share your
        video content except as necessary to provide the Service or as required
        by law. Live video segments are buffered briefly in your organization's
        isolated in-memory cache for playback; recordings and snapshots are
        stored locally on your CloudNode.
      </p>
      <p>
        You are solely responsible for the legality of content captured,
        stored, and shared through your use of the Service.
      </p>

      <h2>10. Third-Party Services</h2>
      <p>
        The Service relies on third-party providers including Clerk
        (authentication) and Fly.io (hosting). We are not responsible for
        the availability, performance, or policies of these third-party
        services. Outages or changes by these providers may affect the
        Service, and we shall not be liable for any resulting disruption
        or data loss.
      </p>

      <h2>11. Disclaimer of Warranties</h2>
      <p>
        <strong>
          THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT
          WARRANTIES OF ANY KIND, WHETHER EXPRESS, IMPLIED, OR STATUTORY.
          TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, WE DISCLAIM
          ALL WARRANTIES, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES
          OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE,
          NON-INFRINGEMENT, AND ANY WARRANTIES ARISING FROM COURSE OF
          DEALING OR USAGE OF TRADE.
        </strong>
      </p>
      <p>
        <strong>
          WE DO NOT WARRANT THAT THE SERVICE WILL BE UNINTERRUPTED,
          ERROR-FREE, SECURE, OR FREE OF VIRUSES OR OTHER HARMFUL
          COMPONENTS. WE DO NOT WARRANT THAT CAMERAS WILL REMAIN
          CONNECTED, THAT VIDEO WILL BE CAPTURED OR STORED SUCCESSFULLY,
          OR THAT THE SERVICE WILL MEET YOUR SECURITY REQUIREMENTS.
        </strong>
      </p>

      <h2>12. Limitation of Liability</h2>
      <p>
        <strong>
          TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT
          SHALL THE COMPANY, ITS OFFICERS, DIRECTORS, EMPLOYEES, AGENTS,
          OR AFFILIATES BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL,
          CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR ANY LOSS OF PROFITS,
          REVENUE, DATA, GOODWILL, OR OTHER INTANGIBLE LOSSES, ARISING
          FROM OR RELATED TO YOUR USE OF OR INABILITY TO USE THE SERVICE,
          WHETHER BASED ON WARRANTY, CONTRACT, TORT (INCLUDING NEGLIGENCE),
          STRICT LIABILITY, OR ANY OTHER LEGAL THEORY.
        </strong>
      </p>
      <p>
        <strong>
          WITHOUT LIMITING THE FOREGOING, THE COMPANY SHALL NOT BE LIABLE
          FOR ANY DAMAGES ARISING FROM: (A) THE FAILURE OF CAMERAS OR NODES
          TO CAPTURE, TRANSMIT, OR STORE VIDEO; (B) SECURITY INCIDENTS,
          THEFT, PROPERTY DAMAGE, OR PERSONAL INJURY THAT CAMERAS FAILED
          TO RECORD OR PREVENT; (C) SERVICE INTERRUPTIONS OR DOWNTIME;
          (D) UNAUTHORIZED ACCESS TO YOUR ACCOUNT OR DATA; OR (E) ACTIONS
          OF THIRD-PARTY SERVICE PROVIDERS.
        </strong>
      </p>
      <p>
        <strong>
          TO THE EXTENT PERMITTED BY LAW, OUR TOTAL AGGREGATE LIABILITY
          FOR ALL CLAIMS ARISING FROM OR RELATED TO THE SERVICE SHALL NOT
          EXCEED THE TOTAL AMOUNT YOU PAID TO US IN THE TWELVE (12) MONTHS
          IMMEDIATELY PRECEDING THE EVENT GIVING RISE TO THE CLAIM, OR
          FIFTY DOLLARS ($50.00), WHICHEVER IS GREATER.
        </strong>
      </p>

      <h2>13. Indemnification</h2>
      <p>
        You agree to indemnify, defend, and hold harmless the Company, its
        officers, directors, employees, agents, and affiliates from and
        against any and all claims, damages, losses, liabilities, costs,
        and expenses (including reasonable attorneys' fees) arising from
        or related to:
      </p>
      <ul>
        <li>Your use of the Service</li>
        <li>Your violation of these Terms</li>
        <li>Your violation of any applicable law, including surveillance and recording laws</li>
        <li>Any content captured, stored, or shared through your use of the Service</li>
        <li>Any claim by a third party related to your camera deployment or video content</li>
        <li>Your failure to secure your account credentials or API keys</li>
      </ul>

      <h2>14. Termination</h2>
      <p>
        Either party may terminate the agreement at any time. You may cancel
        your subscription through the billing settings. We may suspend or
        terminate your access for violation of these Terms, non-payment,
        or any other reason at our sole discretion.
      </p>
      <p>
        Upon termination, your access to the Service will cease. Your data
        may be deleted after a reasonable retention period (typically 30
        days). You may use the Full Reset feature in Settings to delete all
        your data before canceling. Sections 3, 4, 9, 11, 12, 13, 16, and
        17 survive termination.
      </p>

      <h2>15. Changes to Terms</h2>
      <p>
        We may update these Terms from time to time. Material changes will
        be communicated through the Service dashboard or via email. Your
        continued use of the Service after changes take effect constitutes
        acceptance of the updated Terms. If you do not agree with the
        updated Terms, you must stop using the Service.
      </p>

      <h2>16. Governing Law and Dispute Resolution</h2>
      <p>
        These Terms shall be governed by and construed in accordance with
        the laws of the State of Washington, without regard to its conflict
        of law provisions. Any disputes arising under these Terms shall be
        resolved in the state or federal courts located in Washington State, and
        you consent to personal jurisdiction in such courts.
      </p>

      <h2>17. General Provisions</h2>
      <p>
        <strong>Severability:</strong> If any provision of these Terms is
        found to be unenforceable, the remaining provisions shall continue
        in full force and effect.
      </p>
      <p>
        <strong>Entire Agreement:</strong> These Terms, together with the
        Privacy Policy, constitute the entire agreement between you and
        the Company regarding the Service and supersede all prior agreements.
      </p>
      <p>
        <strong>Waiver:</strong> The failure to enforce any provision of
        these Terms shall not constitute a waiver of that provision.
      </p>
      <p>
        <strong>Force Majeure:</strong> We shall not be liable for any delay
        or failure to perform resulting from causes outside our reasonable
        control, including but not limited to natural disasters, power
        outages, internet disruptions, government actions, or pandemics.
      </p>
      <p>
        <strong>Assignment:</strong> You may not assign your rights under
        these Terms without our prior written consent. We may assign our
        rights at any time.
      </p>

      <h2>18. Contact</h2>
      <p>
        For questions about these Terms, contact us at{" "}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> or open an
        issue on our{" "}
        <a href="https://github.com/SourceBox-LLC/OpenSentry-Command/issues" target="_blank" rel="noopener noreferrer">
          GitHub repository
        </a>.
      </p>
    </>
  )
}

function PrivacyContent() {
  return (
    <>
      <h1>Privacy Policy</h1>
      <p className="legal-updated">Last updated: {LAST_UPDATED}</p>

      <p>
        This Privacy Policy describes how SourceBox LLC ("Company," "we,"
        "us," or "our") collects, uses, and protects your information when
        you use the SourceBox Sentry Command Center service ("Service").
      </p>

      <h2>1. Information We Collect</h2>

      <h3>Account Information</h3>
      <p>
        When you create an account, we collect your name, email address, and
        organization details through our authentication provider (Clerk).
        We do not store passwords directly. Payment information is processed
        by Stripe through Clerk and is never stored on our servers.
      </p>

      <h3>Camera and Video Data</h3>
      <p>
        Live video segments captured by your CloudNode cameras are pushed
        directly to the Command Center backend, where they are held in an
        in-memory cache only long enough to be served to authorized viewers
        in your organization. Recordings and snapshots stay on your local
        CloudNode device. We do not access, analyze, view, or share your
        video content except as strictly necessary to provide the Service
        (e.g., serving HLS streams to authenticated users in your
        organization).
      </p>

      <h3>Usage and Log Data</h3>
      <p>We collect operational data to provide and secure the Service:</p>
      <ul>
        <li>Stream access logs (who viewed which camera, when, and IP address)</li>
        <li>MCP tool call activity (tool name, API key used, timestamps, and duration)</li>
        <li>Node registration and heartbeat data (hostname, local IP, camera status)</li>
        <li>Audit logs for administrative actions</li>
      </ul>
      <p>
        All log data is automatically deleted after 90 days.
      </p>

      <h3>Codec and Device Information</h3>
      <p>
        Your CloudNode reports video/audio codec information (e.g.,
        H.264 profile, AAC format) to ensure proper HLS stream playback.
        No other device telemetry is collected.
      </p>

      <h2>2. How We Use Your Information</h2>
      <p>We use collected information solely to:</p>
      <ul>
        <li>Provide, maintain, and improve the Service</li>
        <li>Authenticate users and enforce organization-based access control</li>
        <li>Serve HLS video streams with correct codec parameters</li>
        <li>Enforce plan limits (cameras, nodes, MCP rate limits)</li>
        <li>Generate usage statistics visible in your admin dashboard</li>
        <li>Detect and prevent abuse or unauthorized access</li>
        <li>Process payments and manage subscriptions</li>
        <li>Communicate important service updates</li>
      </ul>
      <p>
        We do not use your information for advertising, profiling, or
        any purpose unrelated to providing the Service.
      </p>

      <h2>3. Data Storage and Security</h2>
      <p>We implement the following security measures:</p>
      <ul>
        <li>All API keys are stored as SHA-256 hashes; plaintext keys are never retained</li>
        <li>Live video segments are kept in an isolated in-memory cache per organization and never written to a third-party object store</li>
        <li>All connections use HTTPS with HSTS enforcement</li>
        <li>Authentication is handled by Clerk with industry-standard JWT verification</li>
        <li>Organization data is isolated at the database level using org_id scoping</li>
        <li>Security headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy) are applied to all responses</li>
      </ul>
      <p>
        While we take reasonable measures to protect your data, no method
        of electronic transmission or storage is 100% secure. We cannot
        guarantee absolute security.
      </p>

      <h2>4. Data Sharing</h2>
      <p>
        We do not sell, rent, or trade your personal information or video
        data. We share information only with the following categories of
        third parties, solely as necessary to provide the Service:
      </p>
      <ul>
        <li><strong>Authentication:</strong> Clerk (account management, session handling)</li>
        <li><strong>Payment processing:</strong> Stripe via Clerk (subscription billing)</li>
        <li><strong>Hosting:</strong> Fly.io (application hosting)</li>
        <li><strong>Legal requirements:</strong> When required by law, regulation, subpoena, or legal process</li>
        <li><strong>Safety:</strong> To protect the rights, property, or safety of our users or the public</li>
      </ul>
      <p>
        Each third-party provider operates under their own privacy policy
        and data processing terms. We encourage you to review their policies.
      </p>

      <h2>5. Data Retention</h2>
      <ul>
        <li>Live video segments are held in memory only as long as needed for playback (typically the last ~15 segments per camera) and are evicted automatically</li>
        <li>Recordings and snapshots are stored locally on your CloudNode device, not on our servers</li>
        <li>Stream access logs, MCP activity logs, and audit logs are retained for 90 days, then automatically deleted</li>
        <li>Account data is retained as long as your account is active</li>
        <li>Upon account or organization deletion, all associated data is permanently deleted</li>
        <li>You can delete all your data at any time using the Full Reset feature in Settings</li>
      </ul>

      <h2>6. Your Rights</h2>
      <p>Depending on your jurisdiction, you may have the right to:</p>
      <ul>
        <li><strong>Access:</strong> View your data through the dashboard and admin panel</li>
        <li><strong>Deletion:</strong> Delete all your organization data via Full Reset in Settings, or by deleting your organization</li>
        <li><strong>Portability:</strong> Stream access logs and MCP activity logs are viewable and exportable from the admin dashboard</li>
        <li><strong>Correction:</strong> Update your account information through Clerk's account management</li>
        <li><strong>Objection:</strong> Cancel your account at any time</li>
        <li><strong>Withdraw consent:</strong> Stop using the Service at any time</li>
      </ul>
      <p>
        To exercise any of these rights, contact us at{" "}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        We will respond to requests within 30 days.
      </p>

      <h2>7. International Data Transfers</h2>
      <p>
        The Service is hosted in the United States. If you access the Service
        from outside the United States, your information may be transferred
        to and processed in the United States, where data protection laws
        may differ from those in your jurisdiction. By using the Service,
        you consent to this transfer. If you are located in the European
        Economic Area (EEA), United Kingdom, or other region with data
        transfer regulations, please be aware that we rely on your consent
        and the necessity of processing to provide the Service as the legal
        basis for data transfers.
      </p>

      <h2>8. Cookies</h2>
      <p>
        We use cookies only for authentication session management through
        Clerk. We do not use advertising, analytics, or tracking cookies.
        These cookies are strictly necessary for the Service to function
        and cannot be disabled while using the Service.
      </p>

      <h2>9. Children's Privacy</h2>
      <p>
        The Service is not intended for use by individuals under the age
        of 18. We do not knowingly collect personal information from
        children under 18. If we become aware that a child under 18 has
        provided us with personal information, we will take steps to
        delete such information promptly.
      </p>

      <h2>10. California Privacy Rights (CCPA)</h2>
      <p>
        If you are a California resident, you have additional rights under
        the California Consumer Privacy Act (CCPA), including the right to
        know what personal information we collect, the right to delete your
        information, and the right to opt out of the sale of your
        information. We do not sell personal information. To exercise your
        CCPA rights, contact us at{" "}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>

      <h2>11. Changes to This Policy</h2>
      <p>
        We may update this Privacy Policy from time to time. Material changes
        will be communicated through the Service dashboard or via email.
        Your continued use of the Service after changes take effect
        constitutes acceptance of the updated policy. If you do not agree
        with the updated policy, you must stop using the Service.
      </p>

      <h2>12. Contact</h2>
      <p>
        For privacy-related questions or to exercise your data rights,
        contact us at{" "}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> or open an
        issue on our{" "}
        <a href="https://github.com/SourceBox-LLC/OpenSentry-Command/issues" target="_blank" rel="noopener noreferrer">
          GitHub repository
        </a>.
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
