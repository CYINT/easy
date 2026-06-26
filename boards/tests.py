import os
import json
import shutil
import tempfile
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from .models import Attachment, Board, BoardList, BoardMembership, Card, Checklist, ChecklistItem, Comment, Invitation
from .security import SecurityAuditMiddleware

User = get_user_model()


class EasyBoardTests(TestCase):
    def setUp(self):
        cache.clear()
        self.media_root = tempfile.mkdtemp()
        self.owner = User.objects.create_user(username="owner", email="owner@example.com", password="password-12345")
        self.member = User.objects.create_user(username="member", email="member@example.com", password="password-12345")
        self.outsider = User.objects.create_user(username="outsider", email="outsider@example.com", password="password-12345")
        self.board = Board.objects.create(name="Launch", owner=self.owner)
        BoardMembership.objects.create(board=self.board, user=self.member)
        self.todo = BoardList.objects.create(board=self.board, title="Todo", position=0)
        self.done = BoardList.objects.create(board=self.board, title="Done", position=1)
        self.first = Card.objects.create(board_list=self.todo, title="First", position=0, created_by=self.owner)
        self.second = Card.objects.create(board_list=self.todo, title="Second", position=1, created_by=self.owner)

    def tearDown(self):
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_board_access_is_limited_to_members(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("boards:board_detail", args=[self.board.id]))
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.outsider)
        response = self.client.get(reverse("boards:board_detail", args=[self.board.id]))
        self.assertEqual(response.status_code, 404)

    def test_create_list_and_card(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("boards:create_list", args=[self.board.id]), {"title": "Doing"})
        self.assertEqual(response.status_code, 302)
        doing = BoardList.objects.get(board=self.board, title="Doing")
        self.assertEqual(doing.position, 2)

        response = self.client.post(
            reverse("boards:create_card", args=[doing.id]),
            {"title": "Build auth", "description": "Google SSO and passkeys"},
        )
        self.assertEqual(response.status_code, 302)
        card = Card.objects.get(board_list=doing, title="Build auth")
        self.assertEqual(card.description, "Google SSO and passkeys")

    def test_owner_can_add_and_remove_board_member(self):
        BoardMembership.objects.filter(board=self.board, user=self.outsider).delete()
        self.client.force_login(self.owner)
        with self.assertLogs("easy.security", level="INFO") as logs:
            response = self.client.post(
                reverse("boards:add_board_member", args=[self.board.id]),
                {"email": self.outsider.email, "role": "admin"},
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn("board_member.saved", logs.output[0])
        membership = BoardMembership.objects.get(board=self.board, user=self.outsider)
        self.assertEqual(membership.role, "admin")

        with self.assertLogs("easy.security", level="INFO") as logs:
            response = self.client.post(reverse("boards:remove_board_member", args=[membership.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("board_member.removed", logs.output[0])
        self.assertFalse(BoardMembership.objects.filter(pk=membership.id).exists())

    def test_board_update_and_delete_are_limited_to_owner_or_manager(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("boards:update_board", args=[self.board.id]), {"name": "Denied"})
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("boards:update_board", args=[self.board.id]),
            {"name": "Launch updated", "description": "Updated description"},
        )
        self.assertEqual(response.status_code, 302)
        self.board.refresh_from_db()
        self.assertEqual(self.board.name, "Launch updated")

        response = self.client.post(reverse("boards:delete_board", args=[self.board.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Board.objects.filter(pk=self.board.id).exists())

    def test_list_update_and_delete_are_limited_to_board_managers(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("boards:update_list", args=[self.todo.id]), {"title": "Denied"})
        self.assertEqual(response.status_code, 403)

        BoardMembership.objects.filter(board=self.board, user=self.member).update(role=BoardMembership.ROLE_ADMIN)
        response = self.client.post(reverse("boards:update_list", args=[self.todo.id]), {"title": "Ready"})
        self.assertEqual(response.status_code, 302)
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.title, "Ready")

        response = self.client.post(reverse("boards:delete_list", args=[self.done.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BoardList.objects.filter(pk=self.done.id).exists())

    def test_move_card_between_lists_persists_order(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("boards:move_card", args=[self.second.id]),
            data=json.dumps({"list_id": self.done.id, "position": 0}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        self.second.refresh_from_db()
        self.first.refresh_from_db()
        self.assertEqual(self.second.board_list, self.done)
        self.assertEqual(self.second.position, 0)
        self.assertEqual(self.first.position, 0)

    def test_comments_checklists_and_assignment(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("boards:add_comment", args=[self.first.id]), {"body": "Looks good."})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Comment.objects.filter(card=self.first, body="Looks good.").exists())

        response = self.client.post(reverse("boards:add_checklist", args=[self.first.id]), {"title": "Ship"})
        self.assertEqual(response.status_code, 302)
        checklist = Checklist.objects.get(card=self.first, title="Ship")

        response = self.client.post(reverse("boards:add_checklist_item", args=[checklist.id]), {"text": "Write docs"})
        self.assertEqual(response.status_code, 302)
        item = checklist.items.get(text="Write docs")

        response = self.client.post(reverse("boards:toggle_checklist_item", args=[item.id]))
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertTrue(item.is_done)

        response = self.client.post(
            reverse("boards:card_detail", args=[self.first.id]),
            {"title": "First updated", "description": "Ready", "assignees": [str(self.member.id)]},
        )
        self.assertEqual(response.status_code, 302)
        self.first.refresh_from_db()
        self.assertEqual(self.first.title, "First updated")
        self.assertEqual(list(self.first.assignees.all()), [self.member])

    def test_card_detail_renders_management_controls(self):
        checklist = Checklist.objects.create(card=self.first, title="Ship")
        ChecklistItem.objects.create(checklist=checklist, text="Write docs", position=0)
        Comment.objects.create(card=self.first, author=self.owner, body="Looks good.")

        self.client.force_login(self.owner)
        response = self.client.get(reverse("boards:card_detail", args=[self.first.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete card")
        self.assertContains(response, "Delete file", count=0)
        self.assertContains(response, "Checklist item text")

    def test_card_delete_removes_card(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("boards:delete_card", args=[self.first.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Card.objects.filter(pk=self.first.id).exists())

    def test_comment_delete_is_limited_to_author_or_board_manager(self):
        comment = Comment.objects.create(card=self.first, author=self.member, body="Member note")

        self.client.force_login(self.outsider)
        response = self.client.post(reverse("boards:delete_comment", args=[comment.id]))
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.owner)
        response = self.client.post(reverse("boards:delete_comment", args=[comment.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Comment.objects.filter(pk=comment.id).exists())

    def test_checklist_item_update_reorder_toggle_and_delete(self):
        checklist = Checklist.objects.create(card=self.first, title="Ship")
        first = ChecklistItem.objects.create(checklist=checklist, text="Write docs", position=0)
        second = ChecklistItem.objects.create(checklist=checklist, text="Run tests", position=1)

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("boards:update_checklist_item", args=[second.id]),
            {"text": "Run full tests", "position": 0},
        )
        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(second.text, "Run full tests")
        self.assertEqual(second.position, 0)
        self.assertEqual(first.position, 1)

        response = self.client.post(reverse("boards:toggle_checklist_item", args=[second.id]))
        self.assertEqual(response.status_code, 302)
        second.refresh_from_db()
        self.assertTrue(second.is_done)

        response = self.client.post(reverse("boards:delete_checklist_item", args=[second.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ChecklistItem.objects.filter(pk=second.id).exists())
        first.refresh_from_db()
        self.assertEqual(first.position, 0)

    @override_settings(EASY_ATTACHMENT_ALLOWED_TYPES=["image/png"], EASY_ATTACHMENT_MAX_BYTES=1024 * 1024)
    def test_attachment_upload_and_download_are_permission_checked(self):
        with override_settings(MEDIA_ROOT=self.media_root):
            self.client.force_login(self.owner)
            upload = SimpleUploadedFile("sample.png", b"fake-png", content_type="image/png")
            with self.assertLogs("easy.security", level="INFO") as logs:
                response = self.client.post(reverse("boards:add_attachment", args=[self.first.id]), {"file": upload})
            self.assertEqual(response.status_code, 302)
            self.assertIn("attachment.uploaded", logs.output[0])
            attachment = Attachment.objects.get(card=self.first)

            response = self.client.get(reverse("boards:download_attachment", args=[attachment.id]))
            self.assertEqual(response.status_code, 200)

            self.client.force_login(self.outsider)
            response = self.client.get(reverse("boards:download_attachment", args=[attachment.id]))
            self.assertEqual(response.status_code, 404)

    @override_settings(EASY_ATTACHMENT_ALLOWED_TYPES=["image/png"], EASY_ATTACHMENT_MAX_BYTES=1024 * 1024)
    def test_attachment_validation_and_delete(self):
        with override_settings(MEDIA_ROOT=self.media_root):
            self.client.force_login(self.owner)
            upload = SimpleUploadedFile("sample.txt", b"text", content_type="text/plain")
            response = self.client.post(reverse("boards:add_attachment", args=[self.first.id]), {"file": upload})
            self.assertEqual(response.status_code, 302)
            self.assertFalse(Attachment.objects.filter(card=self.first).exists())

            upload = SimpleUploadedFile("sample.png", b"fake-png", content_type="image/png")
            response = self.client.post(reverse("boards:add_attachment", args=[self.first.id]), {"file": upload})
            self.assertEqual(response.status_code, 302)
            attachment = Attachment.objects.get(card=self.first)

            with self.assertLogs("easy.security", level="INFO") as logs:
                response = self.client.post(reverse("boards:delete_attachment", args=[attachment.id]))
            self.assertEqual(response.status_code, 302)
            self.assertIn("attachment.deleted", logs.output[0])
            self.assertFalse(Attachment.objects.filter(pk=attachment.id).exists())

    @override_settings(
        EASY_ATTACHMENT_ALLOWED_TYPES=["image/png"],
        EASY_ATTACHMENT_MAX_BYTES=1024 * 1024,
        EASY_UPLOAD_RATE_LIMIT="1/h",
    )
    def test_attachment_upload_is_rate_limited(self):
        with override_settings(MEDIA_ROOT=self.media_root):
            self.client.force_login(self.owner)
            first_upload = SimpleUploadedFile("first.png", b"fake-png", content_type="image/png")
            response = self.client.post(reverse("boards:add_attachment", args=[self.first.id]), {"file": first_upload})
            self.assertEqual(response.status_code, 302)

            second_upload = SimpleUploadedFile("second.png", b"fake-png", content_type="image/png")
            with self.assertLogs("easy.security", level="INFO") as logs:
                response = self.client.post(
                    reverse("boards:add_attachment", args=[self.first.id]),
                    {"file": second_upload},
                )
            self.assertEqual(response.status_code, 429)
            self.assertIn("rate_limit.exceeded", logs.output[0])


class EasyAuthFoundationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_auth_routes_are_available(self):
        route_names = [
            "account_signup",
            "account_login",
            "account_reset_password",
            "account_logout",
            "mfa_index",
            "mfa_activate_totp",
            "mfa_view_recovery_codes",
            "mfa_add_webauthn",
        ]
        for route_name in route_names:
            with self.subTest(route_name=route_name):
                self.assertTrue(reverse(route_name))

    def test_google_login_route_is_not_enabled_by_default(self):
        self.assertFalse(settings.EASY_ENABLE_GOOGLE_OAUTH)
        with self.assertRaises(NoReverseMatch):
            reverse("google_login")

    def test_email_password_registration_requires_invitation(self):
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "new@example.com",
                "password1": "strong-password-12345",
                "password2": "strong-password-12345",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

        invitation = Invitation.objects.create(email="new@example.com")
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "new@example.com",
                "password1": "strong-password-12345",
                "password2": "strong-password-12345",
                "invite_code": invitation.code,
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="new@example.com")
        invitation.refresh_from_db()
        self.assertEqual(invitation.used_by, user)
        self.assertFalse(invitation.is_active)
        self.client.post(reverse("account_logout"))

        with self.assertLogs("easy.security", level="INFO") as logs:
            response = self.client.post(
                reverse("account_login"),
                {"login": "new@example.com", "password": "strong-password-12345"},
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn("auth.login", logs.output[0])

        response = self.client.post(reverse("account_logout"))
        self.assertEqual(response.status_code, 302)

        response = self.client.post(reverse("account_reset_password"), {"email": "new@example.com"})
        self.assertEqual(response.status_code, 302)

    def test_invitation_email_binding_is_enforced(self):
        invitation = Invitation.objects.create(email="invited@example.com")
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "other@example.com",
                "password1": "strong-password-12345",
                "password2": "strong-password-12345",
                "invite_code": invitation.code,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="other@example.com").exists())
        invitation.refresh_from_db()
        self.assertIsNone(invitation.used_by)

    def test_auth_security_settings_are_production_safe_when_debug_is_false(self):
        with override_settings(
            DEBUG=False,
            SECURE_SSL_REDIRECT=True,
            SESSION_COOKIE_SECURE=True,
            CSRF_COOKIE_SECURE=True,
            ACCOUNT_UNIQUE_EMAIL=True,
        ):
            self.assertTrue(settings.SECURE_SSL_REDIRECT)
            self.assertTrue(settings.SESSION_COOKIE_SECURE)
            self.assertTrue(settings.CSRF_COOKIE_SECURE)
            self.assertTrue(settings.ACCOUNT_UNIQUE_EMAIL)
            self.assertEqual(settings.ACCOUNT_RATE_LIMITS["login_failed"], "5/5m")
            self.assertEqual(settings.ACCOUNT_RATE_LIMITS["signup"], "10/h")
            self.assertEqual(settings.ACCOUNT_RATE_LIMITS["password_reset"], "5/h")
            self.assertEqual(settings.EASY_UPLOAD_RATE_LIMIT, "20/h")

    @override_settings(
        EASY_ENABLE_GOOGLE_OAUTH=True,
        SOCIALACCOUNT_PROVIDERS={
            "google": {
                "SCOPE": ["profile", "email"],
                "AUTH_PARAMS": {"access_type": "online"},
            }
        },
    )
    def test_google_provider_can_be_feature_flagged_from_environment_settings(self):
        provider = settings.SOCIALACCOUNT_PROVIDERS["google"]
        self.assertEqual(provider["SCOPE"], ["profile", "email"])
        self.assertEqual(provider["AUTH_PARAMS"], {"access_type": "online"})

    def test_bootstrap_admin_creates_environment_defined_superuser(self):
        stdout = StringIO()
        env = {
            "EASY_ADMIN_EMAIL": "admin@example.com",
            "EASY_ADMIN_USERNAME": "admin",
            "EASY_ADMIN_PASSWORD": "admin-password-12345",
        }
        with patch.dict(os.environ, env):
            call_command("bootstrap_admin", stdout=stdout)

        user = User.objects.get(email="admin@example.com")
        self.assertEqual(user.username, "admin")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("admin-password-12345"))

    def test_login_failure_is_audited(self):
        with self.assertLogs("easy.security", level="INFO") as logs:
            response = self.client.post(
                reverse("account_login"),
                {"login": "missing@example.com", "password": "wrong-password"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("auth.login_failed", "\n".join(logs.output))

    def test_mfa_post_changes_are_audited_by_middleware(self):
        user = User.objects.create_user(username="mfa", email="mfa@example.com", password="password-12345")
        request = RequestFactory().post("/accounts/2fa/totp/activate/")
        request.user = user
        middleware = SecurityAuditMiddleware(lambda request: HttpResponse(status=302))

        with self.assertLogs("easy.security", level="INFO") as logs:
            response = middleware(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("mfa.changed", logs.output[0])

    def test_mfa_audit_skips_failed_changes(self):
        request = RequestFactory().post("/accounts/2fa/totp/activate/")
        request.user = AnonymousUser()
        middleware = SecurityAuditMiddleware(lambda request: HttpResponse(status=403))

        with self.assertNoLogs("easy.security", level="INFO"):
            response = middleware(request)

        self.assertEqual(response.status_code, 403)
