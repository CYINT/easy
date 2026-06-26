import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the environment-defined Easy administrator account."

    def handle(self, *args, **options):
        email = os.environ.get("EASY_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("EASY_ADMIN_PASSWORD", "")
        username = os.environ.get("EASY_ADMIN_USERNAME", "admin").strip() or "admin"

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
            base_username = username
            suffix = 1
            while User.objects.filter(username__iexact=username).exists():
                suffix += 1
                username = f"{base_username}{suffix}"
            user = User(email=email, username=username)
        update_fields = []

        if user.email != email:
            user.email = email
            update_fields.append("email")
        if not user.username:
            user.username = username
            update_fields.append("username")
        if not user.is_staff:
            user.is_staff = True
            update_fields.append("is_staff")
        if not user.is_superuser:
            user.is_superuser = True
            update_fields.append("is_superuser")
        if not user.is_active:
            user.is_active = True
            update_fields.append("is_active")

        user.set_password(password)
        if not created:
            update_fields.append("password")

        if created:
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created Easy administrator account for {email}."))
        elif update_fields:
            user.save(update_fields=sorted(set(update_fields)))
            self.stdout.write(self.style.SUCCESS(f"Updated Easy administrator account for {email}."))
        else:
            self.stdout.write("Easy administrator account already exists.")
