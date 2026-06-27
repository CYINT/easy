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

from .models import AgentToken, Attachment, Board, BoardList, BoardMembership, Card, Checklist, ChecklistItem, Comment, Invitation
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


class EasyApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.media_root = tempfile.mkdtemp()
        self.owner = User.objects.create_user(username="owner", email="owner@example.com", password="password-12345")
        self.member = User.objects.create_user(username="member", email="member@example.com", password="password-12345")
        self.outsider = User.objects.create_user(username="outsider", email="outsider@example.com", password="password-12345")
        self.board = Board.objects.create(name="API Launch", owner=self.owner)
        BoardMembership.objects.create(board=self.board, user=self.member)
        self.todo = BoardList.objects.create(board=self.board, title="Todo", position=0)
        self.done = BoardList.objects.create(board=self.board, title="Done", position=1)
        self.card = Card.objects.create(board_list=self.todo, title="First", position=0, created_by=self.owner)

    def tearDown(self):
        shutil.rmtree(self.media_root, ignore_errors=True)

    def api(self, method, path, payload=None):
        data = json.dumps(payload or {}) if payload is not None else None
        return getattr(self.client, method)(path, data=data, content_type="application/json")

    def test_api_requires_authentication(self):
        response = self.client.get("/api/v1/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "authentication_required")

    def test_api_board_list_detail_and_create_flow(self):
        self.client.force_login(self.owner)

        response = self.client.get("/api/v1/boards")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["boards"][0]["name"], "API Launch")

        response = self.api("post", "/api/v1/boards", {"name": "Agent Board", "description": "Created over API"})
        self.assertEqual(response.status_code, 201)
        board_id = response.json()["board"]["id"]

        response = self.api("post", f"/api/v1/boards/{board_id}/lists", {"title": "Inbox"})
        self.assertEqual(response.status_code, 201)
        list_id = response.json()["list"]["id"]

        response = self.api("post", f"/api/v1/lists/{list_id}/cards", {"title": "Draft contract"})
        self.assertEqual(response.status_code, 201)
        card_id = response.json()["card"]["id"]

        response = self.client.get(f"/api/v1/boards/{board_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["board"]
        self.assertEqual(payload["name"], "Agent Board")
        self.assertEqual(payload["lists"][0]["cards"][0]["id"], card_id)

    def test_api_move_card_between_lists(self):
        self.client.force_login(self.owner)
        response = self.api("post", f"/api/v1/cards/{self.card.id}/move", {"listId": self.done.id, "position": 0})
        self.assertEqual(response.status_code, 200)
        self.card.refresh_from_db()
        self.assertEqual(self.card.board_list, self.done)
        self.assertEqual(response.json()["card"]["listId"], self.done.id)

    def test_api_members_and_assignees_flow(self):
        BoardMembership.objects.filter(board=self.board, user=self.outsider).delete()
        self.client.force_login(self.owner)

        response = self.api("post", f"/api/v1/boards/{self.board.id}/members", {"email": self.outsider.email, "role": "admin"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["membership"]["user"]["email"], self.outsider.email)
        self.assertEqual(response.json()["membership"]["role"], "admin")

        response = self.api("patch", f"/api/v1/cards/{self.card.id}", {"assigneeIds": [self.member.id, self.outsider.id]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([user["email"] for user in response.json()["card"]["assignees"]], [self.member.email, self.outsider.email])

        response = self.client.get(f"/api/v1/boards/{self.board.id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["board"]
        self.assertEqual(payload["members"][1]["user"]["email"], self.outsider.email)
        self.assertEqual(
            [user["email"] for user in payload["lists"][0]["cards"][0]["assignees"]],
            [self.member.email, self.outsider.email],
        )

    def test_api_checklist_flow(self):
        self.client.force_login(self.owner)

        response = self.api("post", f"/api/v1/cards/{self.card.id}/checklists", {"title": "Ship"})
        self.assertEqual(response.status_code, 201)
        checklist_id = response.json()["checklist"]["id"]

        response = self.api("post", f"/api/v1/checklists/{checklist_id}/items", {"text": "Write docs"})
        self.assertEqual(response.status_code, 201)
        first_item_id = response.json()["item"]["id"]

        response = self.api("post", f"/api/v1/checklists/{checklist_id}/items", {"text": "Run tests"})
        self.assertEqual(response.status_code, 201)
        second_item_id = response.json()["item"]["id"]

        response = self.api(
            "patch",
            f"/api/v1/checklist-items/{second_item_id}",
            {"text": "Run full tests", "position": 0, "isDone": True},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"]["position"], 0)
        self.assertTrue(response.json()["item"]["isDone"])

        response = self.api("post", f"/api/v1/checklist-items/{first_item_id}/toggle", {})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["item"]["isDone"])

        response = self.api("patch", f"/api/v1/checklists/{checklist_id}", {"title": "Ship MVP"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checklist"]["title"], "Ship MVP")

        response = self.client.get(f"/api/v1/boards/{self.board.id}")
        self.assertEqual(response.status_code, 200)
        checklists = response.json()["board"]["lists"][0]["cards"][0]["checklists"]
        self.assertEqual(checklists[0]["title"], "Ship MVP")
        self.assertEqual(checklists[0]["items"][0]["text"], "Run full tests")

        response = self.api("delete", f"/api/v1/checklist-items/{first_item_id}")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ChecklistItem.objects.filter(pk=first_item_id).exists())

        response = self.api("delete", f"/api/v1/checklists/{checklist_id}")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Checklist.objects.filter(pk=checklist_id).exists())

    def test_api_comment_flow_and_permissions(self):
        self.client.force_login(self.owner)

        response = self.api("post", f"/api/v1/cards/{self.card.id}/comments", {"body": "Ready for review"})
        self.assertEqual(response.status_code, 201)
        owner_comment_id = response.json()["comment"]["id"]

        response = self.client.get(f"/api/v1/boards/{self.board.id}")
        self.assertEqual(response.status_code, 200)
        comments = response.json()["board"]["lists"][0]["cards"][0]["comments"]
        self.assertEqual(comments[0]["body"], "Ready for review")

        member_comment = Comment.objects.create(card=self.card, author=self.member, body="Member note")
        self.client.force_login(self.outsider)
        response = self.api("delete", f"/api/v1/comments/{member_comment.id}")
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.owner)
        response = self.api("delete", f"/api/v1/comments/{member_comment.id}")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Comment.objects.filter(pk=member_comment.id).exists())

        response = self.api("delete", f"/api/v1/comments/{owner_comment_id}")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Comment.objects.filter(pk=owner_comment_id).exists())

    @override_settings(EASY_ATTACHMENT_ALLOWED_TYPES=["image/png"], EASY_ATTACHMENT_MAX_BYTES=1024 * 1024)
    def test_api_attachment_flow(self):
        with override_settings(MEDIA_ROOT=self.media_root):
            self.client.force_login(self.owner)
            upload = SimpleUploadedFile("agent.png", b"fake-png", content_type="image/png")
            with self.assertLogs("easy.security", level="INFO") as logs:
                response = self.client.post(f"/api/v1/cards/{self.card.id}/attachments", {"file": upload})
            self.assertEqual(response.status_code, 201)
            self.assertIn("attachment.uploaded", logs.output[0])
            attachment_id = response.json()["attachment"]["id"]
            self.assertEqual(response.json()["attachment"]["originalName"], "agent.png")

            response = self.client.get(f"/api/v1/attachments/{attachment_id}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["attachment"]["downloadUrl"], f"/api/v1/attachments/{attachment_id}/download")

            response = self.client.get(f"/api/v1/attachments/{attachment_id}/download")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"fake-png")

            response = self.client.get(f"/api/v1/boards/{self.board.id}")
            attachments = response.json()["board"]["lists"][0]["cards"][0]["attachments"]
            self.assertEqual(attachments[0]["id"], attachment_id)

            self.client.force_login(self.outsider)
            response = self.client.get(f"/api/v1/attachments/{attachment_id}")
            self.assertEqual(response.status_code, 404)

            self.client.force_login(self.owner)
            with self.assertLogs("easy.security", level="INFO") as logs:
                response = self.api("delete", f"/api/v1/attachments/{attachment_id}")
            self.assertEqual(response.status_code, 204)
            self.assertIn("attachment.deleted", logs.output[0])
            self.assertFalse(Attachment.objects.filter(pk=attachment_id).exists())

    def test_api_denies_non_member_access(self):
        self.client.force_login(self.outsider)
        response = self.client.get(f"/api/v1/boards/{self.board.id}")
        self.assertEqual(response.status_code, 404)

    def test_api_accepts_agent_bearer_token(self):
        raw_token, token = AgentToken.create_token(self.owner, "test-agent", scope=AgentToken.SCOPE_WRITE)

        response = self.client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {raw_token}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["email"], self.owner.email)

        response = self.api_with_token("post", "/api/v1/boards", raw_token, {"name": "Token Board"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["board"]["owner"]["email"], self.owner.email)
        token.refresh_from_db()
        self.assertIsNotNone(token.last_used_at)

    def test_api_enforces_read_only_agent_token_scope(self):
        raw_token, _ = AgentToken.create_token(self.owner, "read-agent", scope=AgentToken.SCOPE_READ)

        response = self.client.get("/api/v1/boards", HTTP_AUTHORIZATION=f"Bearer {raw_token}")
        self.assertEqual(response.status_code, 200)

        response = self.api_with_token("post", "/api/v1/boards", raw_token, {"name": "Denied Board"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "insufficient_scope")
        self.assertFalse(Board.objects.filter(name="Denied Board").exists())

    def test_api_rejects_invalid_agent_bearer_token(self):
        response = self.client.get("/api/v1/me", HTTP_AUTHORIZATION="Bearer easy_invalid")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "authentication_required")

    def api_with_token(self, method, path, token, payload=None):
        data = json.dumps(payload or {}) if payload is not None else None
        return getattr(self.client, method)(
            path,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )


class EasyFrontendTests(TestCase):
    def test_frontend_app_and_assets_are_served(self):
        response = self.client.get("/app/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html")
        self.assertIn(b"Easy Board Client", b"".join(response.streaming_content))

        response = self.client.get("/app/src/app.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response["Content-Type"])

    def test_frontend_asset_route_is_allowlisted(self):
        response = self.client.get("/app/../README.md")
        self.assertEqual(response.status_code, 404)


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
