import json

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .forms import (
    AttachmentForm,
    BoardForm,
    BoardListForm,
    CardForm,
    CardUpdateForm,
    ChecklistForm,
    ChecklistItemForm,
    ChecklistItemUpdateForm,
    CommentForm,
)
from .models import Attachment, Board, BoardMembership, Card, Checklist, ChecklistItem, Comment
from .security import audit_event, rate_limit
from .views import (
    _board_queryset,
    _get_board_for_user,
    _get_card_for_user,
    _get_list_for_user,
    _next_position,
    _normalize_cards,
    _normalize_checklist_items,
)

User = get_user_model()


def _json_error(message, status=400, code="bad_request"):
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def _require_auth(request):
    token_user = getattr(request, "easy_api_user", None)
    if token_user is not None:
        request.user = token_user
        return None
    if not request.user.is_authenticated:
        return _json_error("Authentication required.", status=401, code="authentication_required")
    return None


def _require_write_scope(request):
    token = getattr(request, "easy_agent_token", None)
    if token is not None and token.scope != token.SCOPE_WRITE:
        return _json_error("This agent token is read-only.", status=403, code="insufficient_scope")
    return None


def _require_auth_and_scope(request):
    error = _require_auth(request)
    if error:
        return error
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        return _require_write_scope(request)
    return None


def _payload(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        raise ValueError("Request body must be valid JSON.")


def _user_payload(user):
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "displayName": user.get_full_name() or user.email or user.username,
    }


def _board_payload(board, include_lists=False):
    payload = {
        "id": board.id,
        "name": board.name,
        "description": board.description,
        "owner": _user_payload(board.owner),
        "createdAt": board.created_at.isoformat(),
        "updatedAt": board.updated_at.isoformat(),
    }
    if hasattr(board, "list_count"):
        payload["listCount"] = board.list_count
    if include_lists:
        payload["lists"] = [_list_payload(board_list, include_cards=True) for board_list in board.lists.all()]
        payload["members"] = [_membership_payload(membership) for membership in board.memberships.select_related("user")]
    return payload


def _membership_payload(membership):
    return {
        "id": membership.id,
        "role": membership.role,
        "user": _user_payload(membership.user),
        "createdAt": membership.created_at.isoformat(),
    }


def _list_payload(board_list, include_cards=False):
    payload = {
        "id": board_list.id,
        "boardId": board_list.board_id,
        "title": board_list.title,
        "position": board_list.position,
        "createdAt": board_list.created_at.isoformat(),
        "updatedAt": board_list.updated_at.isoformat(),
    }
    if include_cards:
        payload["cards"] = [_card_payload(card) for card in board_list.cards.all()]
    return payload


def _card_payload(card):
    return {
        "id": card.id,
        "listId": card.board_list_id,
        "boardId": card.board.id,
        "title": card.title,
        "description": card.description,
        "position": card.position,
        "assignees": [_user_payload(user) for user in card.assignees.all()],
        "createdBy": _user_payload(card.created_by) if card.created_by else None,
        "comments": [_comment_payload(comment) for comment in card.comments.all()],
        "checklists": [_checklist_payload(checklist, include_items=True) for checklist in card.checklists.all()],
        "attachments": [_attachment_payload(attachment) for attachment in card.attachments.all()],
        "createdAt": card.created_at.isoformat(),
        "updatedAt": card.updated_at.isoformat(),
    }


def _comment_payload(comment):
    return {
        "id": comment.id,
        "cardId": comment.card_id,
        "body": comment.body,
        "author": _user_payload(comment.author),
        "createdAt": comment.created_at.isoformat(),
    }


def _checklist_payload(checklist, include_items=False):
    payload = {
        "id": checklist.id,
        "cardId": checklist.card_id,
        "title": checklist.title,
        "position": checklist.position,
        "createdAt": checklist.created_at.isoformat(),
    }
    if include_items:
        payload["items"] = [_checklist_item_payload(item) for item in checklist.items.all()]
    return payload


def _checklist_item_payload(item):
    return {
        "id": item.id,
        "checklistId": item.checklist_id,
        "text": item.text,
        "isDone": item.is_done,
        "position": item.position,
        "createdAt": item.created_at.isoformat(),
    }


def _attachment_payload(attachment):
    return {
        "id": attachment.id,
        "cardId": attachment.card_id,
        "originalName": attachment.original_name,
        "contentType": attachment.content_type,
        "size": attachment.size,
        "isImage": attachment.is_image,
        "uploadedBy": _user_payload(attachment.uploaded_by) if attachment.uploaded_by else None,
        "downloadUrl": f"/api/v1/attachments/{attachment.id}/download",
        "createdAt": attachment.created_at.isoformat(),
    }


def _get_checklist_for_user(checklist_id, user):
    checklist = get_object_or_404(Checklist.objects.select_related("card"), pk=checklist_id)
    _get_card_for_user(checklist.card_id, user)
    return checklist


def _get_checklist_item_for_user(item_id, user):
    item = get_object_or_404(ChecklistItem.objects.select_related("checklist", "checklist__card"), pk=item_id)
    _get_card_for_user(item.checklist.card_id, user)
    return item


def _get_attachment_for_user(attachment_id, user):
    attachment = get_object_or_404(Attachment.objects.select_related("card", "uploaded_by"), pk=attachment_id)
    _get_card_for_user(attachment.card_id, user)
    return attachment


def _get_comment_for_user(comment_id, user):
    comment = get_object_or_404(Comment.objects.select_related("card", "author"), pk=comment_id)
    _get_card_for_user(comment.card_id, user)
    return comment


def _get_membership_for_user(membership_id, user):
    membership = get_object_or_404(BoardMembership.objects.select_related("board", "user"), pk=membership_id)
    _get_board_for_user(membership.board_id, user)
    return membership


def _user_can_manage_board(board, user):
    if board.owner_id == user.id:
        return True
    return board.memberships.filter(user=user, role=BoardMembership.ROLE_ADMIN).exists()


@require_http_methods(["GET"])
def api_root(request):
    return JsonResponse(
        {
            "service": "easy",
            "version": "v1",
            "links": {
                "me": "/api/v1/me",
                "boards": "/api/v1/boards",
                "openapi": "/api/v1/openapi.json",
            },
        }
    )


@require_http_methods(["GET"])
def openapi_schema(request):
    return JsonResponse(
        {
            "openapi": "3.1.0",
            "info": {
                "title": "Easy API",
                "version": "v1",
                "description": "Session-authenticated JSON API for Easy boards, lists, cards, members, and comments.",
            },
            "paths": {
                "/api/v1/me": {"get": {"summary": "Return the current authenticated user."}},
                "/api/v1/boards": {
                    "get": {"summary": "List boards visible to the current user."},
                    "post": {"summary": "Create a board owned by the current user."},
                },
                "/api/v1/boards/{boardId}": {
                    "get": {"summary": "Return a board with lists, cards, and members."},
                    "patch": {"summary": "Update board metadata."},
                    "delete": {"summary": "Delete a board owned by the current user."},
                },
                "/api/v1/boards/{boardId}/lists": {"post": {"summary": "Create a list on a board."}},
                "/api/v1/lists/{listId}": {
                    "patch": {"summary": "Update a list title."},
                    "delete": {"summary": "Delete a list and its cards."},
                },
                "/api/v1/boards/{boardId}/members": {"post": {"summary": "Add or update a board member."}},
                "/api/v1/memberships/{membershipId}": {
                    "patch": {"summary": "Update a board member role."},
                    "delete": {"summary": "Remove a board member."},
                },
                "/api/v1/lists/{listId}/cards": {"post": {"summary": "Create a card on a list."}},
                "/api/v1/cards/{cardId}": {
                    "get": {"summary": "Return a card."},
                    "patch": {"summary": "Update a card."},
                    "delete": {"summary": "Delete a card."},
                },
                "/api/v1/cards/{cardId}/move": {"post": {"summary": "Move a card to another position or list."}},
                "/api/v1/cards/{cardId}/comments": {"post": {"summary": "Add a comment to a card."}},
                "/api/v1/comments/{commentId}": {"delete": {"summary": "Delete a comment."}},
                "/api/v1/cards/{cardId}/checklists": {"post": {"summary": "Add a checklist to a card."}},
                "/api/v1/cards/{cardId}/attachments": {"post": {"summary": "Upload an attachment to a card."}},
                "/api/v1/attachments/{attachmentId}": {
                    "get": {"summary": "Return attachment metadata."},
                    "delete": {"summary": "Delete an attachment."},
                },
                "/api/v1/attachments/{attachmentId}/download": {"get": {"summary": "Download attachment bytes."}},
                "/api/v1/checklists/{checklistId}": {
                    "patch": {"summary": "Update a checklist title."},
                    "delete": {"summary": "Delete a checklist."},
                },
                "/api/v1/checklists/{checklistId}/items": {"post": {"summary": "Add a checklist item."}},
                "/api/v1/checklist-items/{itemId}": {
                    "patch": {"summary": "Update checklist item text, position, or done state."},
                    "delete": {"summary": "Delete a checklist item."},
                },
                "/api/v1/checklist-items/{itemId}/toggle": {"post": {"summary": "Toggle checklist item completion."}},
            },
            "components": {
                "securitySchemes": {
                    "bearerToken": {"type": "http", "scheme": "bearer"},
                    "sessionCookie": {"type": "apiKey", "in": "cookie", "name": "sessionid"},
                    "csrfToken": {"type": "apiKey", "in": "header", "name": "X-CSRFToken"},
                }
            },
        }
    )


@require_http_methods(["GET"])
def me(request):
    error = _require_auth_and_scope(request)
    if error:
        return error
    return JsonResponse({"user": _user_payload(request.user)})


@require_http_methods(["GET", "POST"])
def boards(request):
    error = _require_auth_and_scope(request)
    if error:
        return error

    if request.method == "GET":
        visible_boards = _board_queryset(request.user).annotate(list_count=Count("lists", distinct=True)).order_by("name")
        return JsonResponse({"boards": [_board_payload(board) for board in visible_boards]})

    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))

    form = BoardForm({"name": data.get("name", ""), "description": data.get("description", "")})
    if not form.is_valid():
        return _json_error("Board name is required.", status=422, code="validation_error")
    board = form.save(commit=False)
    board.owner = request.user
    board.save()
    return JsonResponse({"board": _board_payload(board)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def board_detail(request, board_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    board = _get_board_for_user(board_id, request.user)

    if request.method == "GET":
        board = (
            Board.objects.filter(pk=board.pk)
            .select_related("owner")
            .prefetch_related(
                "memberships__user",
                "lists__cards__assignees",
                "lists__cards__created_by",
                "lists__cards__comments__author",
                "lists__cards__checklists__items",
                "lists__cards__attachments__uploaded_by",
            )
            .get()
        )
        return JsonResponse({"board": _board_payload(board, include_lists=True)})

    if request.method == "DELETE":
        if board.owner_id != request.user.id:
            return _json_error("Only the board owner can delete this board.", status=403, code="permission_denied")
        board.delete()
        return JsonResponse({}, status=204)

    if not _user_can_manage_board(board, request.user):
        return _json_error("Only board managers can update boards.", status=403, code="permission_denied")
    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))
    form = BoardForm({"name": data.get("name", board.name), "description": data.get("description", board.description)}, instance=board)
    if not form.is_valid():
        return _json_error("Board name is required.", status=422, code="validation_error")
    form.save()
    return JsonResponse({"board": _board_payload(board)})


@require_http_methods(["POST"])
def board_lists(request, board_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    board = _get_board_for_user(board_id, request.user)
    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))
    form = BoardListForm({"title": data.get("title", "")})
    if not form.is_valid():
        return _json_error("List title is required.", status=422, code="validation_error")
    board_list = form.save(commit=False)
    board_list.board = board
    board_list.position = _next_position(board.lists)
    board_list.save()
    return JsonResponse({"list": _list_payload(board_list)}, status=201)


@require_http_methods(["PATCH", "DELETE"])
def list_detail(request, list_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    board_list = _get_list_for_user(list_id, request.user)
    if not _user_can_manage_board(board_list.board, request.user):
        return _json_error("Only board managers can update lists.", status=403, code="permission_denied")

    if request.method == "DELETE":
        board_list.delete()
        return JsonResponse({}, status=204)

    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))
    form = BoardListForm({"title": data.get("title", board_list.title)}, instance=board_list)
    if not form.is_valid():
        return _json_error("List title is required.", status=422, code="validation_error")
    form.save()
    return JsonResponse({"list": _list_payload(board_list)})


@require_http_methods(["POST"])
def list_cards(request, list_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    board_list = _get_list_for_user(list_id, request.user)
    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))
    form = CardForm({"title": data.get("title", ""), "description": data.get("description", "")})
    if not form.is_valid():
        return _json_error("Card title is required.", status=422, code="validation_error")
    card = form.save(commit=False)
    card.board_list = board_list
    card.created_by = request.user
    card.position = _next_position(board_list.cards)
    card.save()
    return JsonResponse({"card": _card_payload(card)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def card_detail(request, card_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    card = _get_card_for_user(card_id, request.user)

    if request.method == "GET":
        return JsonResponse({"card": _card_payload(card)})

    if request.method == "DELETE":
        card.delete()
        return JsonResponse({}, status=204)

    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))
    form = CardUpdateForm(
        {
            "title": data.get("title", card.title),
            "description": data.get("description", card.description),
            "assignees": data.get("assigneeIds", [user.id for user in card.assignees.all()]),
        },
        instance=card,
        board=card.board,
    )
    if not form.is_valid():
        return _json_error("Card update is invalid.", status=422, code="validation_error")
    form.save()
    return JsonResponse({"card": _card_payload(card)})


@require_http_methods(["POST"])
@transaction.atomic
def move_card(request, card_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    card = _get_card_for_user(card_id, request.user)
    try:
        data = _payload(request)
        target_list_id = int(data["listId"])
        position = int(data.get("position", 0))
    except (KeyError, TypeError, ValueError) as error:
        return _json_error(f"Invalid move payload: {error}", status=400)

    target_list = _get_list_for_user(target_list_id, request.user)
    if target_list.board_id != card.board.id:
        return _json_error("Cards can only move within the same board.", status=400)

    old_list = card.board_list
    siblings = list(target_list.cards.exclude(pk=card.pk).order_by("position", "created_at"))
    position = max(0, min(position, len(siblings)))
    siblings.insert(position, card)
    card.board_list = target_list
    card.save(update_fields=["board_list", "updated_at"])
    for index, sibling in enumerate(siblings):
        if sibling.position != index or sibling.board_list_id != target_list.id:
            Card.objects.filter(pk=sibling.pk).update(board_list=target_list, position=index)
    if old_list.id != target_list.id:
        _normalize_cards(old_list)
    return JsonResponse({"card": _card_payload(card)})


@require_http_methods(["POST"])
def card_comments(request, card_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    card = _get_card_for_user(card_id, request.user)
    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))
    form = CommentForm({"body": data.get("body", "")})
    if not form.is_valid():
        return _json_error("Comment cannot be empty.", status=422, code="validation_error")
    comment = form.save(commit=False)
    comment.card = card
    comment.author = request.user
    comment.save()
    return JsonResponse({"comment": _comment_payload(comment)}, status=201)


@require_http_methods(["DELETE"])
def comment_detail(request, comment_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    comment = _get_comment_for_user(comment_id, request.user)
    if comment.author_id != request.user.id and not _user_can_manage_board(comment.card.board, request.user):
        return _json_error("Only the comment author or a board manager can delete this comment.", status=403, code="permission_denied")
    comment.delete()
    return JsonResponse({}, status=204)


@require_http_methods(["POST"])
def card_checklists(request, card_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    card = _get_card_for_user(card_id, request.user)
    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))
    form = ChecklistForm({"title": data.get("title", "")})
    if not form.is_valid():
        return _json_error("Checklist title is required.", status=422, code="validation_error")
    checklist = form.save(commit=False)
    checklist.card = card
    checklist.position = _next_position(card.checklists)
    checklist.save()
    return JsonResponse({"checklist": _checklist_payload(checklist, include_items=True)}, status=201)


@require_http_methods(["PATCH", "DELETE"])
def checklist_detail(request, checklist_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    checklist = _get_checklist_for_user(checklist_id, request.user)

    if request.method == "DELETE":
        checklist.delete()
        return JsonResponse({}, status=204)

    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))
    form = ChecklistForm({"title": data.get("title", checklist.title)}, instance=checklist)
    if not form.is_valid():
        return _json_error("Checklist title is required.", status=422, code="validation_error")
    form.save()
    return JsonResponse({"checklist": _checklist_payload(checklist, include_items=True)})


@require_http_methods(["POST"])
def checklist_items(request, checklist_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    checklist = _get_checklist_for_user(checklist_id, request.user)
    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))
    form = ChecklistItemForm({"text": data.get("text", "")})
    if not form.is_valid():
        return _json_error("Checklist item text is required.", status=422, code="validation_error")
    item = form.save(commit=False)
    item.checklist = checklist
    item.position = _next_position(checklist.items)
    item.save()
    return JsonResponse({"item": _checklist_item_payload(item)}, status=201)


@require_http_methods(["PATCH", "DELETE"])
@transaction.atomic
def checklist_item_detail(request, item_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    item = _get_checklist_item_for_user(item_id, request.user)
    checklist = item.checklist

    if request.method == "DELETE":
        item.delete()
        _normalize_checklist_items(checklist)
        return JsonResponse({}, status=204)

    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))
    form = ChecklistItemUpdateForm(
        {"text": data.get("text", item.text), "position": data.get("position", item.position)},
        instance=item,
    )
    if not form.is_valid():
        return _json_error("Checklist item update is invalid.", status=422, code="validation_error")
    item = form.save(commit=False)
    if "isDone" in data:
        item.is_done = bool(data["isDone"])
    siblings = list(checklist.items.exclude(pk=item.pk).order_by("position", "created_at"))
    position = max(0, min(item.position, len(siblings)))
    siblings.insert(position, item)
    item.save()
    for index, sibling in enumerate(siblings):
        if sibling.position != index:
            ChecklistItem.objects.filter(pk=sibling.pk).update(position=index)
    item.refresh_from_db()
    return JsonResponse({"item": _checklist_item_payload(item)})


@require_http_methods(["POST"])
def toggle_checklist_item(request, item_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    item = _get_checklist_item_for_user(item_id, request.user)
    item.is_done = not item.is_done
    item.save(update_fields=["is_done"])
    return JsonResponse({"item": _checklist_item_payload(item)})


@require_http_methods(["POST"])
@rate_limit("attachment_upload", "EASY_UPLOAD_RATE_LIMIT")
def card_attachments(request, card_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    card = _get_card_for_user(card_id, request.user)
    form = AttachmentForm(request.POST, request.FILES)
    if not form.is_valid():
        messages = [error for errors in form.errors.values() for error in errors]
        return _json_error(messages[0] if messages else "Attachment upload is invalid.", status=422, code="validation_error")
    uploaded = form.cleaned_data["file"]
    attachment = Attachment.objects.create(
        card=card,
        uploaded_by=request.user,
        file=uploaded,
        original_name=uploaded.name,
        content_type=getattr(uploaded, "content_type", "application/octet-stream"),
        size=uploaded.size,
    )
    audit_event(
        "attachment.uploaded",
        request=request,
        card_id=card.id,
        attachment_id=attachment.id,
        content_type=attachment.content_type,
        size=attachment.size,
    )
    return JsonResponse({"attachment": _attachment_payload(attachment)}, status=201)


@require_http_methods(["GET", "DELETE"])
def attachment_detail(request, attachment_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    attachment = _get_attachment_for_user(attachment_id, request.user)

    if request.method == "GET":
        return JsonResponse({"attachment": _attachment_payload(attachment)})

    if attachment.uploaded_by_id != request.user.id and not _user_can_manage_board(attachment.card.board, request.user):
        return _json_error("Only the uploader or a board manager can delete this attachment.", status=403, code="permission_denied")
    audit_event(
        "attachment.deleted",
        request=request,
        card_id=attachment.card_id,
        attachment_id=attachment.id,
        content_type=attachment.content_type,
        size=attachment.size,
    )
    attachment.file.delete(save=False)
    attachment.delete()
    return JsonResponse({}, status=204)


@require_http_methods(["GET"])
def attachment_download(request, attachment_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    attachment = _get_attachment_for_user(attachment_id, request.user)
    return FileResponse(
        attachment.file.open("rb"),
        as_attachment=False,
        filename=attachment.original_name,
        content_type=attachment.content_type,
    )


@require_http_methods(["POST"])
def board_members(request, board_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    board = _get_board_for_user(board_id, request.user)
    if not _user_can_manage_board(board, request.user):
        return _json_error("Only board managers can add members.", status=403, code="permission_denied")
    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))
    email = str(data.get("email", "")).strip().lower()
    role = data.get("role", BoardMembership.ROLE_MEMBER)
    if role not in {BoardMembership.ROLE_MEMBER, BoardMembership.ROLE_ADMIN}:
        return _json_error("Invalid board role.", status=422, code="validation_error")
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        return _json_error("No Easy user exists with that email address yet.", status=404, code="user_not_found")
    if user == board.owner:
        return _json_error("The board owner already has access.", status=409, code="owner_already_member")
    membership, _ = BoardMembership.objects.update_or_create(board=board, user=user, defaults={"role": role})
    audit_event("board_member.saved", request=request, board_id=board.id, member_user_id=user.id, role=role)
    return JsonResponse({"membership": _membership_payload(membership)})


@require_http_methods(["PATCH", "DELETE"])
@transaction.atomic
def membership_detail(request, membership_id):
    error = _require_auth_and_scope(request)
    if error:
        return error
    membership = _get_membership_for_user(membership_id, request.user)
    board = membership.board
    if not _user_can_manage_board(board, request.user):
        return _json_error("Only board managers can update members.", status=403, code="permission_denied")

    if request.method == "DELETE":
        member_user_id = membership.user_id
        role = membership.role
        for card in Card.objects.filter(board_list__board=board, assignees=membership.user):
            card.assignees.remove(membership.user)
        membership.delete()
        audit_event("board_member.removed", request=request, board_id=board.id, member_user_id=member_user_id, role=role)
        return JsonResponse({}, status=204)

    try:
        data = _payload(request)
    except ValueError as error:
        return _json_error(str(error))
    role = data.get("role", membership.role)
    if role not in {BoardMembership.ROLE_MEMBER, BoardMembership.ROLE_ADMIN}:
        return _json_error("Invalid board role.", status=422, code="validation_error")
    membership.role = role
    membership.save(update_fields=["role"])
    audit_event("board_member.saved", request=request, board_id=board.id, member_user_id=membership.user_id, role=role)
    return JsonResponse({"membership": _membership_payload(membership)})
