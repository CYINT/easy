import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


def _admin_credentials():
    return {
        "email": os.environ.get("EASY_ADMIN_EMAIL", "").strip().lower(),
        "password": os.environ.get("EASY_ADMIN_PASSWORD", ""),
        "username": os.environ.get("EASY_ADMIN_USERNAME", "admin").strip() or "admin",
    }


def _available_username(User, username):
    base_username = username
    suffix = 1
    while User.objects.filter(username__iexact=username).exists():
        suffix += 1
        username = f"{base_username}{suffix}"
    return username


def _update_admin_flags(user, email, username):
    update_fields = []
    desired_values = {
        "email": email,
        "username": user.username or username,
        "is_staff": True,
        "is_superuser": True,
        "is_active": True,
    }
    for field, value in desired_values.items():
        if getattr(user, field) != value:
            setattr(user, field, value)
            update_fields.append(field)
    return update_fields


class Command(BaseCommand):
    help = "Create or update the environment-defined Easy administrator account."

    def handle(self, *args, **options):
        credentials = _admin_credentials()
        email = credentials["email"]
        password = credentials["password"]
        username = credentials["username"]

        if not email:
            self.stdout.write("EASY_ADMIN_EMAIL is not set; skipping administrator bootstrap.")
            return
        if not password:
            self.stdout.write("EASY_ADMIN_PASSWORD is not set; skipping administrator bootstrap.")
            return

        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        created = user is None
        if created:
            username = _available_username(User, username)
            user = User(email=email, username=username)

        update_fields = _update_admin_flags(user, email, username)
        user.set_password(password)
        if not created:
            update_fields.append("password")

        if created:
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created Easy administrator account for {email}."))
        elif update_fields:
            user.save(update_fields=sorted(set(update_fields)))
            self.stdout.write(self.style.SUCCESS(f"Updated Easy administrator account for {email}."))
        else:
            self.stdout.write("Easy administrator account already exists.")
