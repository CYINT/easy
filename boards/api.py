import json

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .forms import BoardForm, BoardListForm, CardForm, CardUpdateForm, CommentForm
from .models import Board, BoardMembership, Card
from .security import audit_event
from .views import _board_queryset, _get_board_for_user, _get_card_for_user, _get_list_for_user, _next_position, _normalize_cards

User = get_user_model()


def _json_error(message, status=400, code="bad_request"):
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def _require_auth(request):
    if not request.user.is_authenticated:
        return _json_error("Authentication required.", status=401, code="authentication_required")
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
                "/api/v1/boards/{boardId}/members": {"post": {"summary": "Add or update a board member."}},
                "/api/v1/lists/{listId}/cards": {"post": {"summary": "Create a card on a list."}},
                "/api/v1/cards/{cardId}": {
                    "get": {"summary": "Return a card."},
                    "patch": {"summary": "Update a card."},
                    "delete": {"summary": "Delete a card."},
                },
                "/api/v1/cards/{cardId}/move": {"post": {"summary": "Move a card to another position or list."}},
                "/api/v1/cards/{cardId}/comments": {"post": {"summary": "Add a comment to a card."}},
            },
            "components": {
                "securitySchemes": {
                    "sessionCookie": {"type": "apiKey", "in": "cookie", "name": "sessionid"},
                    "csrfToken": {"type": "apiKey", "in": "header", "name": "X-CSRFToken"},
                }
            },
        }
    )


@require_http_methods(["GET"])
def me(request):
    error = _require_auth(request)
    if error:
        return error
    return JsonResponse({"user": _user_payload(request.user)})


@require_http_methods(["GET", "POST"])
def boards(request):
    error = _require_auth(request)
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
    error = _require_auth(request)
    if error:
        return error
    board = _get_board_for_user(board_id, request.user)

    if request.method == "GET":
        board = (
            Board.objects.filter(pk=board.pk)
            .select_related("owner")
            .prefetch_related("memberships__user", "lists__cards__assignees", "lists__cards__created_by")
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
    error = _require_auth(request)
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


@require_http_methods(["POST"])
def list_cards(request, list_id):
    error = _require_auth(request)
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
    error = _require_auth(request)
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
    error = _require_auth(request)
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
    error = _require_auth(request)
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


@require_http_methods(["POST"])
def board_members(request, board_id):
    error = _require_auth(request)
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
