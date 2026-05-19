# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Aether Forge, please report it responsibly.

**Do NOT open a public GitHub issue.**

Email **ask@heyelsa.ai** with:
- Description of the vulnerability
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
| < 0.1   | No        |

## Security Practices

- All secrets loaded from environment variables, never hardcoded
- `.env` files created with 0600 permissions
- `.ows/` vaults created with 0700 permissions
- Parameterized SQL queries throughout (no string concatenation)
- Prompt injection scanning on all external input
- Rate limiting on A2A server (60 req/min per IP)
- 1MB max request body on A2A server
- Servers bind to 127.0.0.1 by default
- Kill switch blocks all side effects instantly
- AES-256-GCM encrypted wallet backups
