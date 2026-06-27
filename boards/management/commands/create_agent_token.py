from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from boards.models import AgentToken


class Command(BaseCommand):
    help = "Create an Easy API bearer token for an existing user. The raw token is shown once."

    def add_arguments(self, parser):
        parser.add_argument("user", help="User email or username.")
        parser.add_argument("--name", default="agent", help="Human-readable token name.")
        parser.add_argument("--scope", choices=[AgentToken.SCOPE_READ, AgentToken.SCOPE_WRITE], default=AgentToken.SCOPE_READ)
        parser.add_argument("--expires-days", type=int, default=90, help="Token lifetime in days. Use 0 for no expiry.")

    def handle(self, *args, **options):
        identifier = options["user"].strip()
        User = get_user_model()
        user = User.objects.filter(email__iexact=identifier).first() or User.objects.filter(username__iexact=identifier).first()
        if not user:
            raise CommandError(f"No user found for {identifier}.")
        if not user.is_active:
            raise CommandError(f"User {identifier} is not active.")

        expires_days = options["expires_days"]
        expires_at = None if expires_days == 0 else timezone.now() + timedelta(days=expires_days)
        raw_token, token = AgentToken.create_token(
            user=user,
            name=options["name"].strip() or "agent",
            expires_at=expires_at,
            scope=options["scope"],
        )

        self.stdout.write(self.style.SUCCESS(f"Created Easy {token.scope} agent token {token.id} for {user.email or user.username}."))
        if expires_at:
            self.stdout.write(f"Expires at: {expires_at.isoformat()}")
        self.stdout.write("Copy this token now. It is stored only as a hash and cannot be shown again.")
        self.stdout.write(raw_token)
