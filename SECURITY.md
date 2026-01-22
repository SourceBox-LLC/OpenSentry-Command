# Security Policy

OpenSentry is a security-focused application and we take security vulnerabilities seriously. We appreciate your efforts to responsibly disclose your findings.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |
| < 1.0   | :x:                |

We recommend always running the latest version of OpenSentry.

## Security Features

OpenSentry implements multiple layers of security:

| Feature | Description |
|---------|-------------|
| **HTTPS** | Web dashboard encrypted with TLS (port 5000) |
| **RTSPS** | Video streams encrypted with TLS (port 8322) |
| **MQTT/TLS** | Control commands encrypted (port 8883) |
| **Password Hashing** | Bcrypt with automatic salt |
| **Session Security** | Secure cookies, configurable timeout |
| **CSRF Protection** | Token-based protection on forms |
| **Rate Limiting** | Brute force protection on login |
| **Account Lockout** | Automatic lockout after failed attempts |
| **Input Validation** | Whitelist-based command validation |
| **Security Headers** | CSP, X-Frame-Options, X-Content-Type-Options |

## Reporting a Vulnerability

### DO NOT

- Open a public GitHub issue for security vulnerabilities
- Disclose the vulnerability publicly before it's fixed
- Access or modify other users' data without permission

### DO

1. **Email us directly** at: security@sourcebox-llc.com

2. **Include in your report:**
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)
   - Your contact information

3. **Allow time for response:**
   - We will acknowledge receipt within 48 hours
   - We will provide a detailed response within 7 days
   - We will keep you informed of our progress

### What to Expect

1. **Acknowledgment** - We'll confirm we received your report
2. **Assessment** - We'll investigate and assess the severity
3. **Fix Development** - We'll develop and test a fix
4. **Release** - We'll release the fix and credit you (if desired)
5. **Disclosure** - We'll coordinate public disclosure timing with you

## Scope

### In Scope

- OpenSentry Command Center (web application, API)
- Camera Node communication protocols
- Authentication and authorization
- Data storage and encryption
- Docker container security

### Out of Scope

- Denial of Service attacks
- Social engineering
- Physical security
- Third-party dependencies (report to upstream)
- Issues requiring physical access to the device

## Security Best Practices for Users

### Deployment

1. **Use strong passwords** - Minimum 12 characters with mixed case, numbers, symbols
2. **Keep software updated** - Run `git pull && docker compose up --build -d` regularly
3. **Use a firewall** - Only expose necessary ports
4. **Use Tailscale** - For remote access instead of port forwarding
5. **Change default credentials** - Never use default usernames/passwords in production

### Network Security

1. **Isolate IoT devices** - Use a separate VLAN for cameras if possible
2. **Disable UPnP** - Prevent automatic port forwarding
3. **Monitor access logs** - Check for unauthorized access attempts

### Data Security

1. **Backup your database** - Regular backups of `data/opensentry.db`
2. **Rotate secrets** - Regenerate `OPENSENTRY_SECRET` periodically
3. **Audit users** - Remove unused accounts

## Known Security Considerations

### Self-Signed Certificates

OpenSentry generates self-signed SSL certificates by default. While encrypted, these are not verified by a trusted CA. For production deployments with external access, consider:

- Using a reverse proxy (nginx, Caddy) with Let's Encrypt certificates
- Adding the CA certificate to your trust store

### Local Network Trust

OpenSentry is designed for local network deployment. The threat model assumes:

- Your local network is trusted
- Cameras and Command Center are on the same network
- Remote access is through VPN (Tailscale recommended)

If deploying on an untrusted network, additional security measures are recommended.

## Security Updates

Security updates are released as soon as possible after a vulnerability is confirmed. Monitor:

- [GitHub Releases](https://github.com/SourceBox-LLC/OpenSentry-Command/releases)
- [GitHub Security Advisories](https://github.com/SourceBox-LLC/OpenSentry-Command/security/advisories)

## Contact

- **Security issues**: security@sourcebox-llc.com
- **General questions**: [GitHub Discussions](https://github.com/SourceBox-LLC/OpenSentry-Command/discussions)
- **Bug reports**: [GitHub Issues](https://github.com/SourceBox-LLC/OpenSentry-Command/issues)

---

Thank you for helping keep OpenSentry secure!
