# Easy

Easy is an open-source, self-hosted team board for visual work tracking. It provides boards, lists, cards, comments, checklists, assignments, attachments, and drag-and-drop movement without plugin or automation overhead.

Easy is designed to run on local infrastructure and can be served publicly behind HTTPS at `easy.kuzuryu.ai`.

## Features

- Email/password accounts through Django and django-allauth.
- Google SSO through django-allauth social login.
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

## MVP Boundaries

Included: users, boards, lists, cards, comments, images/attachments, descriptions, assignments, checklists, drag/drop, Google SSO, email/password login, MFA/passkeys, HTTPS, backup/restore documentation, and local self-hosting.

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
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Then open `http://127.0.0.1:8000`.

## Google SSO

Set these environment variables when a Google OAuth client is ready:

```text
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
```

Recommended redirect URI:

```text
https://easy.kuzuryu.ai/accounts/google/login/callback/
```

Do not commit Google OAuth secrets. CYINT local credentials should remain outside this repository.

## MFA And Passkeys

MFA and passkey support are enabled through django-allauth. After signing in, use the account security pages to enroll TOTP, recovery codes, or WebAuthn/passkey credentials.

The local navigation includes an `MFA and passkeys` link to `/accounts/2fa/`.

## Docker Deployment

Dan's local bridge host reads secrets from `C:\Users\Dan\.cyint\easy\easy.env` by default:

```powershell
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

## DNS And HTTPS

For `easy.kuzuryu.ai`, create an AWS Route 53 record pointing to the selected local ingress target. AWS is used for DNS only.

Caddy terminates HTTPS and automatically manages certificates only when the `edge` profile is enabled and the hostname is publicly reachable on ports `80`/`443`.

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

## Core Workflow API

The MVP route and permission contract is documented in `docs/core-workflow-api.md`.

## Verification

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
docker compose config
```

## Security Notes

- Use a strong `DJANGO_SECRET_KEY` in production.
- Set `DJANGO_DEBUG=false` for public hosting.
- Keep `DJANGO_SECURE_SSL_REDIRECT=true`, `DJANGO_SESSION_COOKIE_SECURE=true`, and `DJANGO_CSRF_COOKIE_SECURE=true` behind HTTPS.
- Keep allauth rate limits enabled for login, signup, and password reset; tune upload throttling with `EASY_UPLOAD_RATE_LIMIT`.
- Preserve `easy.security` logs in production log collection; they contain JSON audit events without raw secrets or file contents.
- Expose only ports `80` and `443` to the public internet.
- Keep PostgreSQL and media storage private.
- Do not commit `.env`, OAuth secrets, database dumps, uploaded media, or local backups.
