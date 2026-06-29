# Easy

[![CI](https://github.com/CYINT/easy/actions/workflows/ci.yml/badge.svg)](https://github.com/CYINT/easy/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/CYINT/easy/branch/main/graph/badge.svg)](https://codecov.io/gh/CYINT/easy)

Easy is an open-source, self-hosted team board for visual work tracking. It provides boards, lists, cards, comments, checklists, assignments, attachments, and drag-and-drop movement without plugin or automation overhead.

Easy is designed to run on self-managed infrastructure and can be served publicly behind HTTPS on the hostname you configure.

## Features

- Email/password accounts through Django and django-allauth.
- Optional Google SSO through django-allauth social login.
- MFA and passkey support through django-allauth MFA/WebAuthn.
- Boards with owner/member access control.
- Ordered lists and cards.
- Card title, description, assigned users, comments, checklists, and attachments.
- Image attachment previews and permission-checked attachment downloads.
- Animated drag/drop card movement within and between lists.
- Docker Compose deployment with PostgreSQL and optional Caddy HTTPS reverse proxy.
- Rate limits for login, signup, password reset, and attachment uploads.
- Security audit logs for login attempts, MFA/passkey changes, board membership changes, and attachment uploads/deletes.
- Health endpoint at `/health/`.
- Agent-friendly JSON API under `/api/v1/` with bearer-token support.
- Separate frontend shell under `frontend/` that consumes the API instead of Django model routes.
- Easy-branded account shell for login, signup, password reset, and MFA/passkey management.

## MVP Boundaries

Included: users, boards, lists, cards, comments, images/attachments, descriptions, assignments, checklists, drag/drop, email/password login, MFA/passkeys, HTTPS, backup/restore documentation, and local self-hosting. Google SSO is present as an opt-in feature flag, disabled by default.

Excluded from the MVP: plugin marketplace, power features, workflow automations, billing, native mobile apps, and AWS application hosting.

## License

Easy is licensed under `AGPL-3.0-or-later`. See `LICENSE`.

## Local Development

Requirements:

- Python 3.13 or newer
- PostgreSQL for production-like local work, or SQLite for simple development

Quick start:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py bootstrap_admin
.\.venv\Scripts\python.exe manage.py runserver
```

Then open `http://127.0.0.1:8000`.

## Google SSO

Google SSO is disabled by default. It has not been manually tested for a production release. Enable it only after configuring and validating a Google OAuth web client for your deployment hostname.

Set these environment variables when a Google OAuth client is ready:

```text
EASY_ENABLE_GOOGLE_OAUTH=true
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
```

Redirect URI format:

```text
https://<your-hostname>/accounts/google/login/callback/
```

Validate the deployed OAuth client configuration with:

```powershell
npm run qa:google-oauth-probe
```

The probe must reach Google without `redirect_uri_mismatch` before the MVP release is tagged.

Do not commit Google OAuth secrets or local credential files.

## MFA And Passkeys

MFA and passkey support are enabled through django-allauth. After signing in, use the account security pages to enroll TOTP, recovery codes, or WebAuthn/passkey credentials.

The local navigation includes a configurable MFA link to `/accounts/2fa/`.

Customize the app and MFA display names with:

```text
EASY_APP_NAME=Easy
EASY_MFA_DISPLAY_NAME=MFA and passkeys
```

These names affect the Django UI shell and account/MFA pages. They do not change the Python package name, Docker service names, database names, API paths, or license.

## Administrator And Invitations

Easy is invite-only. Public self-signup requires a one-time invite created by an administrator in Django admin.

Set these environment variables before first startup:

```text
EASY_ADMIN_EMAIL=admin@example.com
EASY_ADMIN_USERNAME=admin
EASY_ADMIN_PASSWORD=...
```

`python manage.py bootstrap_admin` creates or updates that account as an active staff superuser. The Docker entrypoint runs it after migrations. Do not commit the real administrator password.

To invite a user, sign in at `/admin/`, create an `Invitation`, and send the generated invite link to the user out of band. The invite may be bound to a specific email address or left unbound. Each invite can be used once.

Invite links use this format:

```text
https://<your-hostname>/accounts/signup/?invite=<invite-code>
```

When a user opens the link, Easy lands on signup with the invite code prefilled. If the invitation is bound to a specific email address, the signup email field is prefilled too. The user then sets their password, creates the account, and can enroll MFA or passkeys after signing in.

## Docker Deployment

Create a local env file before starting the stack:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

For a fresh standalone host, create an env file first:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

The default Compose stack runs:

- `easy`: Django/Gunicorn app
- `db`: PostgreSQL

The app publishes Gunicorn to loopback by default at `127.0.0.1:18082`. PostgreSQL remains private to the Compose network.

To run Caddy as the HTTPS edge on a host where public ports `80` and `443` route directly to this machine:

```powershell
docker compose --profile edge up --build -d
```

Before creating a public release tag, complete the release checklist in `docs/release-checklist.md`.

## DNS And HTTPS

Create a DNS record for your configured hostname pointing to the selected ingress target. If you use AWS Route 53, Easy only needs DNS records there; it does not require AWS application hosting.

Caddy terminates HTTPS and automatically manages certificates only when the `edge` profile is enabled and the hostname is publicly reachable on ports `80`/`443`. A deployment may also satisfy public ingress with a DNS-published AAAA record when the host's IPv6 address serves HTTPS directly.

Check the current public-ingress posture with:

```powershell
npm run qa:public-ingress-probe
```

Check all release gates before tagging with:

```powershell
$env:EASY_RELEASE_HOSTNAME="<your-hostname>"
npm run qa:release-gates
```

The release gate verifies that GitHub Actions CI passed on the exact commit being tagged.
It also verifies that `/health/` exposes `release.commit` for the deployed app and that the value matches the commit being tagged. Set `EASY_RELEASE_COMMIT` to the deployed Git SHA when starting the stack.

The guarded tag helper runs the same gates and defaults to a dry run:

```powershell
npm run release:tag -- v0.1.0 --dry-run
```

For an explicitly accepted private beta, set `EASY_RELEASE_NOTES_PATH` to release notes that state the private-network or tunnel access boundary.

## Backups

PostgreSQL backup:

```powershell
docker compose exec -T db pg_dump --clean --if-exists -U easy easy > easy-db-backup.sql
```

PostgreSQL restore:

```powershell
Get-Content .\easy-db-backup.sql | docker compose exec -T db psql -U easy easy
```

Attachment backup:

```powershell
docker run --rm -v easy_easy_media:/media -v ${PWD}:/backup alpine tar czf /backup/easy-media-backup.tgz -C /media .
```

Attachment restore:

```powershell
docker run --rm -v easy_easy_media:/media -v ${PWD}:/backup alpine sh -c "cd /media && tar xzf /backup/easy-media-backup.tgz"
```

Test both database and attachment restore before relying on a public deployment.

## Upgrades

Before upgrading, create fresh database and media backups, move to the target tag or commit, rebuild the Compose stack, and verify the deployment. See `docs/upgrade.md`.

## Backend API And Frontend Boundary

Agents and standalone frontends should use the JSON API documented in `docs/agent-api.md`. The API root is `/api/v1/`, and `/api/v1/openapi.json` exposes a compact OpenAPI schema.

Programmatic agents can use scoped bearer tokens generated for existing users. Read-only is the default:

```powershell
.\.venv\Scripts\python.exe manage.py create_agent_token admin@example.com --name local-agent
```

Use `--scope write` only when an agent needs to mutate boards. The raw token is shown once and stored only as a hash. Revoke tokens in Django admin by disabling the token.

The legacy Django template routes remain available as a compatibility UI. New frontend work belongs under `frontend/` and should use `frontend/src/api.js`.

The older server-rendered route and permission contract is documented in `docs/core-workflow-api.md`.

## UI Shells

Easy currently has three UI surfaces:

- Django application shell in `templates/base.html` for server-rendered boards and account links.
- allauth account shell in `templates/allauth/layouts/` for login, signup, password reset, and MFA/passkey management.
- API-driven frontend shell in `frontend/` for standalone client work against `/api/v1/`.

Keep new standalone product UI work in `frontend/`. Keep auth/account customizations in the allauth layout overrides unless a specific allauth form needs its own template.

UI work should follow `docs/ui-quality-standard.md`. The standard is intentionally opinionated for an operational board: WCAG 2.2 AA basics, restrained visual styling, reliable card movement, and E2E checks for overflow, focus, contrast, target sizing, and drop-zone usability.

## Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe scripts\quality-gates.py
.\.venv\Scripts\python.exe -m coverage run manage.py test
.\.venv\Scripts\python.exe -m coverage report
npm run qa:ui-quality
docker compose config --quiet
```

The Python quality gate enforces Radon cyclomatic complexity rank `B` or better for application code and maintainability index rank `C` or better. Coverage is configured in `pyproject.toml` and fails below `80%` for non-test application code.

GitHub Actions publishes `coverage.xml` to Codecov when the repository is connected to Codecov and a `CODECOV_TOKEN` secret is configured.

## Security Notes

- Use a strong `DJANGO_SECRET_KEY` in production.
- Set `DJANGO_DEBUG=false` for public hosting.
- Keep `DJANGO_SECURE_SSL_REDIRECT=true`, `DJANGO_SESSION_COOKIE_SECURE=true`, and `DJANGO_CSRF_COOKIE_SECURE=true` behind HTTPS.
- Keep allauth rate limits enabled for login, signup, and password reset; tune upload throttling with `EASY_UPLOAD_RATE_LIMIT`.
- Preserve `easy.security` logs in production log collection; they contain JSON audit events without raw secrets or file contents.
- Expose only ports `80` and `443` to the public internet.
- Keep PostgreSQL and media storage private.
- Do not commit `.env`, OAuth secrets, database dumps, uploaded media, or local backups.
