import hashlib
import json
import logging
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

security_logger = logging.getLogger("easy.security")


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def audit_event(action, request=None, user=None, **details):
    actor = user or getattr(request, "user", None)
    payload = {
        "action": action,
        "user_id": getattr(actor, "id", None) if getattr(actor, "is_authenticated", False) else None,
        "ip": _client_ip(request) if request is not None else None,
        "path": getattr(request, "path", None),
        **details,
    }
    security_logger.info(json.dumps(payload, sort_keys=True, default=str))


def _parse_rate(rate):
    count, window = rate.split("/", 1)
    seconds_by_unit = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
    }
    if window.isdigit():
        return int(count), int(window)
    multiplier = int(window[:-1] or "1")
    return int(count), multiplier * seconds_by_unit[window[-1]]


def _rate_key(request, scope):
    actor = request.user.id if request.user.is_authenticated else _client_ip(request)
    raw = f"{scope}:{actor}:{request.path}"
    return "easy-rate:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def rate_limit(scope, setting_name):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            limit, window = _parse_rate(getattr(settings, setting_name))
            key = _rate_key(request, scope)
            current = cache.get(key, 0)
            if current >= limit:
                audit_event("rate_limit.exceeded", request=request, scope=scope, limit=limit, window_seconds=window)
                return JsonResponse({"error": "Rate limit exceeded."}, status=429)
            if current == 0:
                cache.set(key, 1, window)
            else:
                cache.incr(key)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


class SecurityAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.method == "POST" and request.path.startswith("/accounts/2fa/") and response.status_code < 400:
            audit_event("mfa.changed", request=request, status_code=response.status_code)
        return response
