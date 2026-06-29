from allauth.account.views import SignupView

from .models import Invitation


class InviteSignupView(SignupView):
    def get_initial(self):
        initial = super().get_initial()
        code = (self.request.GET.get("invite") or self.request.GET.get("invite_code") or "").strip()
        if not code:
            return initial

        initial["invite_code"] = code
        invitation = Invitation.objects.filter(
            code=code,
            is_active=True,
            used_at__isnull=True,
            used_by__isnull=True,
        ).first()
        if invitation and invitation.email:
            initial["email"] = invitation.email
        return initial
