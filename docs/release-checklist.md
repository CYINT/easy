# Easy MVP Release Checklist

Use this checklist before creating a public release tag.

## Required Gates

- Confirm `main` is pushed to `https://github.com/CYINT/easy`.
- Confirm public CI is passing on the exact commit to be tagged.
- Confirm no credentials, local `.env` files, database dumps, uploaded media, OAuth secrets, or backup archives are committed.
- Confirm `DJANGO_DEBUG=false` and production cookie/security settings are active in the deployment environment.
- Confirm `EASY_ENABLE_GOOGLE_OAUTH=false` unless Google OAuth is explicitly in release scope.
- If Google OAuth is enabled, confirm `npm run qa:google-oauth-probe` passes for the deployed hostname without `redirect_uri_mismatch`.
- Confirm Google OAuth remains documented as not manually tested if it is not part of the release.
- Confirm `bootstrap_admin` created or updated the intended administrator from environment variables.
- Confirm public signup requires an administrator-created invite code.
- Confirm email/password login works for the administrator.
- Confirm MFA/passkey enrollment is available from the account security pages.
- Confirm `/health/`, `/app/`, and `/api/v1/openapi.json` return HTTP 200 over HTTPS on the deployment hostname.
- Confirm board, list, card, comment, checklist, attachment, assignment, and member-management workflows pass a smoke test.
- Confirm database and media backup commands run successfully.
- Confirm a restore has been tested before relying on the deployment for production data.
- Confirm `easy.security` logs are retained by the host log collection path.

## Public Ingress Gate

Before a public internet release, choose and verify one accepted ingress posture:

- Public HTTPS: WAN ports `80` and `443` route only to the Easy HTTPS edge for the configured hostname.
- Explicit private beta: the release notes state that access is limited to the approved private network or tunnel, and the decision owner accepts that the hostname is not publicly reachable.

Run:

```powershell
$env:EASY_HOSTNAME="<your-hostname>"
npm run qa:public-ingress-probe
```

For a public HTTPS release, the probe must show that WAN `443` reaches the Easy hostname.

For a private beta release, record the accepted access boundary in the release notes and do not describe the deployment as publicly reachable.

## Tagging

After all applicable gates pass:

```powershell
git status --short
git tag -a v0.1.0 -m "Easy MVP release"
git push origin v0.1.0
```

Do not create or push the tag while any required gate is unresolved.
