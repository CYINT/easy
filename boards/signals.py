from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from .security import audit_event


@receiver(user_logged_in)
def audit_user_logged_in(sender, request, user, **kwargs):
    audit_event("auth.login", request=request, user=user)


@receiver(user_login_failed)
def audit_user_login_failed(sender, credentials, request, **kwargs):
    username = credentials.get("username") or credentials.get("email") or credentials.get("login")
    audit_event("auth.login_failed", request=request, username=username)
