from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from allauth.account.forms import SignupForm

from .models import Attachment, Board, BoardList, BoardMembership, Card, Checklist, ChecklistItem, Comment, Invitation

User = get_user_model()


class InviteSignupForm(SignupForm):
    invite_code = forms.CharField(
        label="Invite code",
        max_length=96,
        help_text="Ask your Easy administrator for an invite code.",
    )

    def clean_invite_code(self):
        code = self.cleaned_data["invite_code"].strip()
        if not Invitation.objects.filter(code=code, is_active=True, used_at__isnull=True, used_by__isnull=True).exists():
            raise forms.ValidationError("This invite code is invalid or has already been used.")
        return code

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        code = cleaned.get("invite_code")
        if email and code:
            invitation = Invitation.objects.filter(code=code).first()
            if invitation and not invitation.can_be_used_by(email):
                raise forms.ValidationError("This invite code is not valid for that email address.")
        return cleaned


class BoardForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class BoardListForm(forms.ModelForm):
    class Meta:
        model = BoardList
        fields = ["title"]


class BoardMemberForm(forms.Form):
    email = forms.EmailField()
    role = forms.ChoiceField(choices=BoardMembership.ROLE_CHOICES, initial=BoardMembership.ROLE_MEMBER)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if not User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("No Easy user exists with that email address yet.")
        return email


class CardForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = ["title", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class CardUpdateForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = ["title", "description", "assignees"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "assignees": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, board=None, **kwargs):
        super().__init__(*args, **kwargs)
        if board is not None:
            self.fields["assignees"].queryset = board.member_users()


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "placeholder": "Add a comment..."})}


class ChecklistForm(forms.ModelForm):
    class Meta:
        model = Checklist
        fields = ["title"]


class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ["text"]


class ChecklistItemUpdateForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ["text", "position"]
        widgets = {"position": forms.NumberInput(attrs={"min": 0})}


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ["file"]

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        max_bytes = settings.EASY_ATTACHMENT_MAX_BYTES
        allowed_types = set(settings.EASY_ATTACHMENT_ALLOWED_TYPES)
        content_type = getattr(uploaded, "content_type", "")
        if uploaded.size > max_bytes:
            raise forms.ValidationError(f"Attachment is too large. Maximum size is {max_bytes // (1024 * 1024)} MB.")
        if content_type not in allowed_types:
            raise forms.ValidationError("This file type is not allowed for attachments.")
        return uploaded
