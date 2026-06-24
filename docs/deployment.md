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
- Create the Route 53 record for `easy.kuzuryu.ai` pointing to the local ingress target.
- Run `docker compose up --build -d`.
- Run migrations and create the first superuser if needed.
- Verify `https://easy.kuzuryu.ai/health/` returns `{"status":"ok","service":"easy"}`.

## Local Ingress Decision Still Required

Before go-live, select the concrete public ingress pattern:

- static WAN IP with router port forwarding to the Easy host;
- dynamic DNS target that Route 53 can track; or
- a non-AWS tunnel/reverse-proxy route terminating at the Easy host.

Do not expose the wider LAN while enabling the Easy route.
