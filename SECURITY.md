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
- Public hosts should expose only ports `80` and `443`.
