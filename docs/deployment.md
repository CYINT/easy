# Easy Deployment Notes

## Target Hostname

Set `EASY_HOSTNAME`, `DJANGO_ALLOWED_HOSTS`, and `DJANGO_CSRF_TRUSTED_ORIGINS` for your deployment hostname. Example:

```text
EASY_HOSTNAME=boards.example.com
DJANGO_ALLOWED_HOSTS=boards.example.com,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://boards.example.com
```

## Hosting Boundary

Easy is intended to run on self-managed infrastructure. AWS is optional and should be needed only for DNS if you choose Route 53.

## Production Checklist

- Create `.env` from `.env.example` and replace all placeholder secrets.
- Set `EASY_ADMIN_EMAIL`, `EASY_ADMIN_USERNAME`, and `EASY_ADMIN_PASSWORD` before first startup.
- Confirm `DJANGO_DEBUG=false`.
- Confirm `DJANGO_ALLOWED_HOSTS` contains your deployment hostname.
- Confirm `DJANGO_CSRF_TRUSTED_ORIGINS` contains your HTTPS deployment origin.
- Confirm only ports `80` and `443` are publicly exposed.
- Confirm PostgreSQL is not publicly exposed.
- Leave `EASY_ENABLE_GOOGLE_OAUTH=false` unless you are explicitly releasing Google SSO.
- Google OAuth has not been manually tested for a production release.
- If enabling Google OAuth, configure redirect URI `https://<your-hostname>/accounts/google/login/callback/` and verify with `npm run qa:google-oauth-probe`; it must not report `redirect_uri_mismatch`.
- Confirm `EASY_UPLOAD_RATE_LIMIT` is set for expected public traffic.
- Confirm the `easy.security` logger is collected by the host log retention path.
- Create the DNS record for your hostname pointing to the local ingress target.
- Run `docker compose --profile edge up --build -d` on a host where Caddy should terminate public HTTPS, or `docker compose up --build -d` on Dan's current local bridge host.
- Run migrations and create the first superuser if needed.
- Confirm `python manage.py bootstrap_admin` created or updated the first administrator.
- Confirm public signup requires a one-time administrator-created invitation code.
- Verify `https://<your-hostname>/health/` returns `{"status":"ok","service":"easy"}`.

## Local Bridge Deployment

When Easy is routed by a shared HTTPS bridge rather than by the Compose Caddy service, the default Compose profile starts only the database and app services so Caddy does not compete for port `443`:

```powershell
docker compose up --build -d
```

Set `EASY_ENV_FILE` before running Compose if your local secrets live outside `.env`.

The `easy` service publishes Gunicorn only to loopback by default:

```text
127.0.0.1:18082 -> easy:8000
```

The shared local HTTPS bridge then routes:

```text
<your-hostname> -> http://127.0.0.1:18082
```

Do not set `EASY_BIND_ADDRESS=0.0.0.0` unless the firewall/router exposure has been reviewed and approved.

## Local Ingress Decision Still Required

Before go-live, select the concrete public ingress pattern:

- static WAN IP with router port forwarding to the Easy host;
- dynamic DNS target that Route 53 can track; or
- a non-AWS tunnel/reverse-proxy route terminating at the Easy host.

Use `npm run qa:public-ingress-probe` to check whether WAN `443` reaches the Easy hostname and whether a local UPnP gateway exposes an existing `443` mapping.

Do not expose the wider LAN while enabling the Easy route.
