from django.db import transaction
from django.utils import timezone
from allauth.account.adapter import DefaultAccountAdapter

from .models import Invitation


class InviteOnlyAccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form, commit=True):
        with transaction.atomic():
            invitation = Invitation.objects.select_for_update().get(code=form.cleaned_data["invite_code"])
            user = super().save_user(request, user, form, commit=commit)
            invitation.used_by = user
            invitation.used_at = timezone.now()
            invitation.is_active = False
            invitation.save(update_fields=["used_by", "used_at", "is_active"])
            return user
