# Security Policy

Thank you for helping keep ZeroBot and its users safe.

## Reporting a vulnerability

**Please do not file a public GitHub issue for security vulnerabilities.**

Instead, contact the maintainer privately:

- Telegram: [@iLildev](https://t.me/iLildev)
- Email (preferred for sensitive reports): file a private GitHub
  Security Advisory at <https://github.com/iLildev/zerobot/security/advisories/new>

We aim to:

- Acknowledge your report within **48 hours**.
- Provide a remediation timeline within **7 days**.
- Credit you (if you wish) in the release notes that ship the fix.

## Supported versions

ZeroBot is in early alpha (`0.x`). Only the `main` branch receives
security updates. Once a stable `1.0` ships, this section will be
expanded.

## Scope

In-scope vulnerability classes:

- Authentication / authorization bypass on `/admin/*` routes.
- Sandbox escape from the Builder Agent (writing or reading outside
  `runtime_envs/builder_sessions/{user_id}/workspace`).
- Forged events accepted by the Manager Bot when
  `EVENT_SHARED_SECRET` is configured.
- SQL injection or other injection paths.
- Crystal billing bypass (e.g. unbilled bot creation, infinite top-up).
- Denial of service vectors that survive the configured rate limits and
  hibernation timeouts.

Out of scope:

- Misconfiguration in the operator's own deployment (e.g. running the
  admin console without `ADMIN_TOKEN`).
- Issues that require a host-level compromise.
- Third-party dependencies — please report those upstream.

## Hardening recommendations for operators

- Always set `ADMIN_TOKEN` to a long, random string (≥ 32 bytes).
- Always set `EVENT_SHARED_SECRET` in production so Manager Bot rejects
  unsigned events.
- Run the Builder Agent's sandbox under a dedicated unprivileged user;
  the bundled `Dockerfile` does this by default.
- Tune `SANDBOX_*` env vars to match your hardware budget.
- Front the public services (gateway, user console) with a TLS-terminating
  reverse proxy (Caddy, nginx, Traefik).
- Treat the Builder Bot as **trusted-user-only** until namespace-based
  isolation lands. Filesystem-level sandboxing is not a substitute for
  containers when serving untrusted users.
