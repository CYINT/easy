# Security Policy

Report suspected vulnerabilities privately to the CYINT maintainers before public disclosure.

Do not include secrets, live credentials, private keys, production database dumps, uploaded user files, or OAuth client secrets in issues, pull requests, commits, screenshots, or public logs.

## Supported Version

The current `main` branch and latest tagged release are supported during the MVP period.

## Baseline Controls

- Public deployments must use HTTPS.
- Production deployments must set `DJANGO_DEBUG=false`.
- Google OAuth secrets must be supplied through environment variables or local secret storage.
- Attachment downloads are permission checked by the Django app.
- Login failures, signup, password reset, and attachment uploads are rate limited.
- Security audit events are logged through the `easy.security` logger for login attempts, MFA/passkey route changes, board membership changes, and attachment uploads/deletes.
- Public hosts should expose only ports `80` and `443`.

## Production Log Handling

Forward application logs to the host's normal log retention path before public use. Treat audit logs as operational evidence: do not publish them publicly, and do not add raw credentials, database dumps, uploaded files, or OAuth tokens to log messages.
