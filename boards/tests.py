import json
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Attachment, Board, BoardList, BoardMembership, Card, Checklist, Comment

User = get_user_model()


class EasyBoardTests(TestCase):
    def setUp(self):
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
        response = self.client.post(
            reverse("boards:add_board_member", args=[self.board.id]),
            {"email": self.outsider.email, "role": "admin"},
        )
        self.assertEqual(response.status_code, 302)
        membership = BoardMembership.objects.get(board=self.board, user=self.outsider)
        self.assertEqual(membership.role, "admin")

        response = self.client.post(reverse("boards:remove_board_member", args=[membership.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BoardMembership.objects.filter(pk=membership.id).exists())

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

    @override_settings(EASY_ATTACHMENT_ALLOWED_TYPES=["image/png"], EASY_ATTACHMENT_MAX_BYTES=1024 * 1024)
    def test_attachment_upload_and_download_are_permission_checked(self):
        with override_settings(MEDIA_ROOT=self.media_root):
            self.client.force_login(self.owner)
            upload = SimpleUploadedFile("sample.png", b"fake-png", content_type="image/png")
            response = self.client.post(reverse("boards:add_attachment", args=[self.first.id]), {"file": upload})
            self.assertEqual(response.status_code, 302)
            attachment = Attachment.objects.get(card=self.first)

            response = self.client.get(reverse("boards:download_attachment", args=[attachment.id]))
            self.assertEqual(response.status_code, 200)

            self.client.force_login(self.outsider)
            response = self.client.get(reverse("boards:download_attachment", args=[attachment.id]))
            self.assertEqual(response.status_code, 404)
