# Easy Deployment Notes

## Target Hostname

`easy.kuzuryu.ai`

## Hosting Boundary

Easy is intended to run on local CYINT/Dan infrastructure. AWS should be used only for Route 53 DNS records for the hostname.

## Production Checklist

- Create `.env` from `.env.example` and replace all placeholder secrets.
- Confirm `DJANGO_DEBUG=false`.
- Confirm `DJANGO_ALLOWED_HOSTS` contains `easy.kuzuryu.ai`.
- Confirm `DJANGO_CSRF_TRUSTED_ORIGINS` contains `https://easy.kuzuryu.ai`.
- Confirm only ports `80` and `443` are publicly exposed.
- Confirm PostgreSQL is not publicly exposed.
- Configure Google OAuth redirect URI: `https://easy.kuzuryu.ai/accounts/google/login/callback/`.
- Verify Google OAuth configuration with `npm run qa:google-oauth-probe`; it must not report `redirect_uri_mismatch`.
- Confirm `EASY_UPLOAD_RATE_LIMIT` is set for expected public traffic.
- Confirm the `easy.security` logger is collected by the host log retention path.
- Create the Route 53 record for `easy.kuzuryu.ai` pointing to the local ingress target.
- Run `docker compose --profile edge up --build -d` on a host where Caddy should terminate public HTTPS, or `docker compose up --build -d` on Dan's current local bridge host.
- Run migrations and create the first superuser if needed.
- Verify `https://easy.kuzuryu.ai/health/` returns `{"status":"ok","service":"easy"}`.

## Local Bridge Deployment

On Dan's current local bridge host, Easy is routed by the shared HTTPS bridge rather than by the Compose Caddy service. The default Compose profile starts only the database and app services so Caddy does not compete for port `443`:

```powershell
docker compose up --build -d
```

This host reads secrets from `C:\Users\Dan\.cyint\easy\easy.env` by default. To use a different env file, set `EASY_ENV_FILE` before running Compose.

The `easy` service publishes Gunicorn only to loopback by default:

```text
127.0.0.1:18082 -> easy:8000
```

The shared local HTTPS bridge then routes:

```text
easy.kuzuryu.ai -> http://127.0.0.1:18082
```

Do not set `EASY_BIND_ADDRESS=0.0.0.0` unless the firewall/router exposure has been reviewed and approved.

## Local Ingress Decision Still Required

Before go-live, select the concrete public ingress pattern:

- static WAN IP with router port forwarding to the Easy host;
- dynamic DNS target that Route 53 can track; or
- a non-AWS tunnel/reverse-proxy route terminating at the Easy host.

Use `npm run qa:public-ingress-probe` to check whether WAN `443` reaches the Easy hostname and whether a local UPnP gateway exposes an existing `443` mapping.

Do not expose the wider LAN while enabling the Easy route.
