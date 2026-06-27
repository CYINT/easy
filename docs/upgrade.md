# Easy Upgrade Guide

Use this guide when updating an existing self-hosted Easy deployment.

## Before Upgrading

- Read the release notes for the target version.
- Confirm the target commit or tag is from `https://github.com/CYINT/easy`.
- Confirm GitHub Actions CI passed for the exact commit or tag.
- Confirm the deployment environment still sets production-safe values such as `DJANGO_DEBUG=false`, secure cookies, allowed hosts, CSRF trusted origins, and administrator bootstrap variables.
- Set `EASY_RELEASE_COMMIT` to the target Git SHA before rebuilding so release gates can prove the live deployment matches the target.
- Confirm `EASY_ENABLE_GOOGLE_OAUTH=false` unless Google OAuth is explicitly in release scope and has been validated.
- Create fresh database and media backups before pulling or rebuilding.

## Backup First

Database:

```powershell
docker compose exec -T db pg_dump --clean --if-exists -U easy easy > easy-db-pre-upgrade.sql
```

Media:

```powershell
docker run --rm -v easy_easy_media:/media -v ${PWD}:/backup alpine tar czf /backup/easy-media-pre-upgrade.tgz -C /media .
```

Keep these files outside Git.

## Upgrade

Fetch the target release and rebuild:

```powershell
git fetch --tags origin
git checkout <target-tag-or-commit>
docker compose pull
docker compose up --build -d
```

The application container runs migrations and administrator bootstrap on startup. For manual validation, run:

```powershell
docker compose exec -T easy python manage.py check
```

## Verify

Confirm the deployment responds over HTTPS:

```powershell
curl.exe -sS https://<your-hostname>/health/
curl.exe -sS https://<your-hostname>/api/v1/openapi.json
```

Then run the release gates for the accepted release posture:

```powershell
$env:EASY_RELEASE_HOSTNAME="<your-hostname>"
npm run qa:release-gates
```

If this is an explicitly accepted private beta, also set:

```powershell
$env:EASY_RELEASE_PRIVATE_BETA_ACCEPTED="true"
$env:EASY_RELEASE_NOTES_PATH="docs/release-notes/v0.1.0-private-beta.md"
```

## Roll Back

If validation fails, stop the app, restore the last known-good code, and restore the pre-upgrade backups:

```powershell
git checkout <previous-tag-or-commit>
docker compose up --build -d db
Get-Content .\easy-db-pre-upgrade.sql | docker compose exec -T db psql -U easy easy
docker run --rm -v easy_easy_media:/media -v ${PWD}:/backup alpine sh -c "cd /media && tar xzf /backup/easy-media-pre-upgrade.tgz"
docker compose up --build -d
```

After rollback, verify `/health/`, `/app/`, `/api/v1/openapi.json`, login, and a representative board workflow.
