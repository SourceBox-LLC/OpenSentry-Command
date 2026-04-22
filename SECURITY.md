# Security Policy

SourceBox Sentry is a security-focused application and we take vulnerabilities seriously.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.1.x (FastAPI) | :white_check_mark: |
| 2.0.x (FastAPI) | :x: |
| < 2.0 (Flask)   | :x: |

Always run the latest version. The current release is tracked in `backend/pyproject.toml` (`version = "2.1.0"` at time of writing) and surfaced by `GET /api/health`.

## Security Features

| Feature | Description |
|---------|-------------|
| **Clerk Authentication** | JWT-based authentication with organization-scoped permissions |
| **API Key Hashing** | CloudNode API keys stored as SHA-256 hashes |
| **Same-origin Streaming** | Live segments served through the authenticated backend — no third-party storage in the live video path |
| **Tenant Isolation** | All queries scoped by `org_id` -- no cross-org data access |
| **CORS** | Explicit origin allowlist (no wildcards with credentials) |
| **Audit Logging** | Stream access tracked with user ID, IP, and user agent |
| **Encrypted Storage** | CloudNode encrypts API key at rest with AES-256-GCM |
| **Webhook Verification** | Clerk webhooks verified via Svix signature |

## Reporting a Vulnerability

### Do NOT

- Open a public GitHub issue for security vulnerabilities
- Disclose the vulnerability publicly before it is fixed

### Do

1. **Report via**: https://www.sourceboxai.com/security

2. **Include:**
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

3. **Response timeline:**
   - Acknowledgment within 48 hours
   - Assessment within 7 days
   - Fix coordinated with reporter

## Scope

### In Scope

- Command Center API and web application
- CloudNode-to-backend communication
- Authentication and authorization
- Data storage and tenant isolation
- HLS segment cache and playlist serving

### Out of Scope

- Denial of Service attacks
- Social engineering
- Physical access to devices
- Third-party dependencies (report upstream)

## Best Practices for Deployment

1. **Keep software updated** -- pull latest and rebuild regularly
2. **Use strong Clerk passwords** -- enforce via Clerk dashboard settings
3. **Rotate API keys** -- use the key rotation endpoint for CloudNodes periodically
4. **Restrict CORS** -- set `FRONTEND_URL` to your actual domain
5. **Monitor audit logs** -- review stream access logs for unauthorized access
6. **Use HTTPS** -- deploy behind a reverse proxy with TLS (Fly.io handles this)
7. **Backup your database** -- regular backups of the application database

## Security Updates

Monitor:
- [GitHub Releases](https://github.com/SourceBox-LLC/OpenSentry-Command/releases)
- [GitHub Security Advisories](https://github.com/SourceBox-LLC/OpenSentry-Command/security/advisories)

## Contact

- **Security issues**: https://www.sourceboxai.com/security
- **General questions**: [GitHub Discussions](https://github.com/SourceBox-LLC/OpenSentry-Command/discussions)
- **Bug reports**: [GitHub Issues](https://github.com/SourceBox-LLC/OpenSentry-Command/issues)
