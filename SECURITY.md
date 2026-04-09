# Security Policy

OpenSentry is a security-focused application and we take vulnerabilities seriously.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.0.x (FastAPI) | :white_check_mark: |
| < 2.0 (Flask) | :x: |

Always run the latest version.

## Security Features

| Feature | Description |
|---------|-------------|
| **Clerk Authentication** | JWT-based authentication with organization-scoped permissions |
| **API Key Hashing** | CloudNode API keys stored as SHA-256 hashes |
| **Presigned URLs** | Time-limited S3 URLs for all video content (default 5 min) |
| **Tenant Isolation** | All queries scoped by `org_id` -- no cross-org data access |
| **Rate Limiting** | Stream URL generation capped at 10 req/min per IP |
| **CORS** | Explicit origin allowlist (no wildcards with credentials) |
| **Audit Logging** | Stream access tracked with user ID, IP, and user agent |
| **MCP API Key Auth** | MCP tools authenticated via org-scoped Bearer tokens (SHA-256 hashed) |
| **MCP Activity Logging** | Every MCP tool call persisted to DB with tool name, API key, status, and duration |
| **MCP Read-Only Tools** | MCP server exposes only read-only tools — no write operations |
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
- Presigned URL generation and expiry

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
5. **Monitor audit logs** -- review stream access logs and MCP activity logs for unauthorized access
6. **Manage MCP API keys** -- revoke unused keys from the MCP Control Center, monitor tool call history in the Admin Dashboard
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
