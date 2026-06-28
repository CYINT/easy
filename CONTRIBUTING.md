# Contributing

Easy welcomes focused fixes and improvements that keep the project self-hostable, secure, and useful for small teams.

## License

Easy is licensed under `AGPL-3.0-or-later`. By contributing, you agree that your contribution is provided under that license.

## Project Boundaries

- Easy is a self-hosted team board with email/password auth, MFA/passkeys, invite-only access, boards, cards, comments, checklists, attachments, and an agent-friendly API.
- The backend is Django.
- The JSON API lives under `/api/v1/` and is documented in `docs/agent-api.md`.
- The API-driven frontend shell lives in `frontend/`.
- The server-rendered compatibility UI lives in `templates/` and `static/easy/`.
- Login, signup, password reset, and MFA/passkey screens are provided by django-allauth and branded through `templates/allauth/layouts/`.

Keep standalone product UI work in `frontend/`. Change Django templates only when maintaining the server-rendered UI, auth/account shell, or admin-facing compatibility workflows.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py bootstrap_admin
.\.venv\Scripts\python.exe manage.py runserver
```

Then open `http://127.0.0.1:8000`.

## Configuration

Useful local branding settings:

```text
EASY_APP_NAME=Easy
EASY_MFA_DISPLAY_NAME=MFA and passkeys
```

These change UI display text only. Do not rename packages, Docker services, database names, API paths, or license identifiers for branding-only work.

Google OAuth is disabled by default behind `EASY_ENABLE_GOOGLE_OAUTH=false`. Do not enable or document it as production-ready unless it has been manually tested for the target hostname.

## Required Checks

Run the focused checks for your change. For most backend or UI work:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
npm run qa:frontend
npm run qa:dragdrop
npm run qa:ui-quality
docker compose config --quiet
```

For release-related changes, also run the release gates described in `docs/release-checklist.md`.

## UI Standards

Follow `docs/ui-quality-standard.md`.

The short version:

- Meet WCAG 2.2 AA basics for contrast, focus visibility, labels, keyboard access, and target size.
- Keep operational surfaces quiet, dense, and scannable.
- Keep cards, panels, inputs, and buttons at `8px` border radius or less.
- Avoid decorative gradients, oversized type inside work surfaces, nested cards, and ornamental shadows.
- Preserve reliable card movement with pointer drag/drop and `Alt+Arrow` keyboard movement.

## Security And Secrets

Do not commit:

- `.env`
- OAuth client secrets
- Django secret keys
- database dumps
- uploaded media
- local backups
- raw bearer tokens
- admin passwords

Use `.env.example` for placeholders only. Raw agent tokens are displayed once and stored only as hashes; never paste real token values into issues, tests, docs, or commits.

## Pull Requests

Before opening a pull request:

- Keep the change small and explain the user-visible impact.
- Add or update tests for behavior changes.
- Update README/docs when setup, security posture, API behavior, or UI standards change.
- Confirm no secrets or generated local artifacts are included.
- Include the checks you ran and any checks you intentionally skipped.
