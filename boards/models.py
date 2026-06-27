from pathlib import Path
import hashlib
import hmac
import secrets
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse

User = get_user_model()


def attachment_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"cards/{instance.card_id}/{uuid4().hex}{suffix}"


class Board(models.Model):
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_easy_boards")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("boards:board_detail", args=[self.pk])

    def user_can_access(self, user):
        if not user.is_authenticated:
            return False
        if self.owner_id == user.id:
            return True
        return self.memberships.filter(user=user).exists()

    def member_users(self):
        return User.objects.filter(Q(id=self.owner_id) | Q(board_memberships__board=self)).distinct()


class BoardMembership(models.Model):
    ROLE_MEMBER = "member"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [(ROLE_MEMBER, "Member"), (ROLE_ADMIN, "Admin")]

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="board_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["board", "user"], name="unique_easy_board_member")]
        ordering = ["user__email", "user__username"]

    def __str__(self):
        return f"{self.user} on {self.board}"


def invite_code():
    return secrets.token_urlsafe(24)


class Invitation(models.Model):
    email = models.EmailField(blank=True, help_text="Optional. Leave blank for any invited email address.")
    code = models.CharField(max_length=96, unique=True, default=invite_code)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_easy_invitations",
    )
    used_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="used_easy_invitations",
    )
    is_active = models.BooleanField(default=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["email", "is_active"]),
        ]

    def __str__(self):
        target = self.email or "any email"
        return f"Invitation for {target}"

    @property
    def is_used(self):
        return self.used_at is not None or self.used_by_id is not None

    def can_be_used_by(self, email):
        if not self.is_active or self.is_used:
            return False
        if self.email and self.email.lower() != email.lower():
            return False
        return True


class AgentToken(models.Model):
    SCOPE_READ = "read"
    SCOPE_WRITE = "write"
    SCOPE_CHOICES = [(SCOPE_READ, "Read"), (SCOPE_WRITE, "Write")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="easy_agent_tokens")
    name = models.CharField(max_length=120)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_READ)
    token_hash = models.CharField(max_length=64, unique=True)
    token_prefix = models.CharField(max_length=16, db_index=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__email", "name"]
        indexes = [
            models.Index(fields=["token_prefix", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} for {self.user}"

    @staticmethod
    def hash_token(raw_token):
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @classmethod
    def create_token(cls, user, name, expires_at=None, scope=SCOPE_READ):
        raw_token = f"easy_{secrets.token_urlsafe(32)}"
        token = cls.objects.create(
            user=user,
            name=name,
            scope=scope,
            token_hash=cls.hash_token(raw_token),
            token_prefix=raw_token[:12],
            expires_at=expires_at,
        )
        return raw_token, token

    def matches(self, raw_token):
        return hmac.compare_digest(self.token_hash, self.hash_token(raw_token))

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())


class BoardList(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="lists")
    title = models.CharField(max_length=180)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "created_at"]
        indexes = [models.Index(fields=["board", "position"])]

    def __str__(self):
        return self.title


class Card(models.Model):
    board_list = models.ForeignKey(BoardList, on_delete=models.CASCADE, related_name="cards")
    title = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_easy_cards")
    assignees = models.ManyToManyField(User, blank=True, related_name="assigned_easy_cards")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "created_at"]
        indexes = [models.Index(fields=["board_list", "position"])]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("boards:card_detail", args=[self.pk])

    @property
    def board(self):
        return self.board_list.board


class Comment(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="easy_comments")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.author} on {self.card}"


class Checklist(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="checklists")
    title = models.CharField(max_length=180, default="Checklist")
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "created_at"]

    def __str__(self):
        return self.title


class ChecklistItem(models.Model):
    checklist = models.ForeignKey(Checklist, on_delete=models.CASCADE, related_name="items")
    text = models.CharField(max_length=260)
    is_done = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "created_at"]

    def __str__(self):
        return self.text


class Attachment(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="easy_attachments")
    file = models.FileField(upload_to=attachment_path)
    original_name = models.CharField(max_length=260)
    content_type = models.CharField(max_length=120)
    size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name

    @property
    def is_image(self):
        return self.content_type.startswith("image/")
