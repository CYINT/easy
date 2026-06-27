import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    AttachmentForm,
    BoardForm,
    BoardListForm,
    BoardMemberForm,
    CardForm,
    CardUpdateForm,
    ChecklistItemUpdateForm,
    ChecklistForm,
    ChecklistItemForm,
    CommentForm,
)
from .models import Attachment, Board, BoardList, BoardMembership, Card, Checklist, ChecklistItem, Comment
from .security import audit_event, rate_limit

User = get_user_model()


def _board_queryset(user):
    return Board.objects.filter(Q(owner=user) | Q(memberships__user=user)).distinct()


def _get_board_for_user(board_id, user):
    return get_object_or_404(_board_queryset(user), pk=board_id)


def _get_list_for_user(list_id, user):
    return get_object_or_404(
        BoardList.objects.filter(Q(board__owner=user) | Q(board__memberships__user=user)).distinct(),
        pk=list_id,
    )


def _get_card_for_user(card_id, user):
    return get_object_or_404(
        Card.objects.select_related("board_list", "board_list__board")
        .filter(Q(board_list__board__owner=user) | Q(board_list__board__memberships__user=user))
        .distinct(),
        pk=card_id,
    )


def _normalize_cards(board_list):
    for index, card in enumerate(board_list.cards.order_by("position", "created_at")):
        if card.position != index:
            Card.objects.filter(pk=card.pk).update(position=index)


def _normalize_checklist_items(checklist):
    for index, item in enumerate(checklist.items.order_by("position", "created_at")):
        if item.position != index:
            ChecklistItem.objects.filter(pk=item.pk).update(position=index)


def _user_can_manage_board(board, user):
    if board.owner_id == user.id:
        return True
    return board.memberships.filter(user=user, role=BoardMembership.ROLE_ADMIN).exists()


def _next_position(queryset):
    return queryset.count()


def _release_payload():
    return {
        "version": settings.EASY_RELEASE_VERSION,
        "commit": settings.EASY_RELEASE_COMMIT,
    }


@require_GET
def health(request):
    return JsonResponse({"status": "ok", "service": "easy", "release": _release_payload()})


def home(request):
    if request.user.is_authenticated:
        return redirect("boards:dashboard")
    return render(request, "boards/home.html")


@login_required
def dashboard(request):
    if request.method == "POST":
        form = BoardForm(request.POST)
        if form.is_valid():
            board = form.save(commit=False)
            board.owner = request.user
            board.save()
            messages.success(request, "Board created.")
            return redirect(board)
    else:
        form = BoardForm()

    boards = _board_queryset(request.user).annotate(list_count=Count("lists", distinct=True)).order_by("name")
    return render(request, "boards/dashboard.html", {"boards": boards, "form": form})


@login_required
def board_detail(request, board_id):
    board = _get_board_for_user(board_id, request.user)
    lists = (
        board.lists.prefetch_related("cards", "cards__assignees", "cards__checklists", "cards__attachments")
        .order_by("position", "created_at")
    )
    return render(
        request,
        "boards/board_detail.html",
        {
            "board": board,
            "lists": lists,
            "list_form": BoardListForm(),
            "board_form": BoardForm(instance=board),
            "member_form": BoardMemberForm(),
            "card_form": CardForm(),
        },
    )


@login_required
@require_POST
def update_board(request, board_id):
    board = _get_board_for_user(board_id, request.user)
    if not _user_can_manage_board(board, request.user):
        return HttpResponseForbidden("Only board managers can update boards.")
    form = BoardForm(request.POST, instance=board)
    if form.is_valid():
        form.save()
        messages.success(request, "Board updated.")
    else:
        messages.error(request, "Board name is required.")
    return redirect(board)


@login_required
@require_POST
def delete_board(request, board_id):
    board = _get_board_for_user(board_id, request.user)
    if board.owner_id != request.user.id:
        return HttpResponseForbidden("Only the board owner can delete this board.")
    board.delete()
    messages.success(request, "Board deleted.")
    return redirect("boards:dashboard")


@login_required
@require_POST
def add_board_member(request, board_id):
    board = _get_board_for_user(board_id, request.user)
    if not _user_can_manage_board(board, request.user):
        return HttpResponseForbidden("Only board managers can add members.")
    form = BoardMemberForm(request.POST)
    if form.is_valid():
        email = form.cleaned_data["email"]
        user = get_object_or_404(User, email__iexact=email)
        if user == board.owner:
            messages.info(request, "The board owner already has access.")
        else:
            BoardMembership.objects.update_or_create(
                board=board,
                user=user,
                defaults={"role": form.cleaned_data["role"]},
            )
            audit_event(
                "board_member.saved",
                request=request,
                board_id=board.id,
                member_user_id=user.id,
                role=form.cleaned_data["role"],
            )
            messages.success(request, "Board member saved.")
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect(board)


@login_required
@require_POST
def remove_board_member(request, membership_id):
    membership = get_object_or_404(BoardMembership.objects.select_related("board"), pk=membership_id)
    board = _get_board_for_user(membership.board_id, request.user)
    if not _user_can_manage_board(board, request.user):
        return HttpResponseForbidden("Only board managers can remove members.")
    audit_event(
        "board_member.removed",
        request=request,
        board_id=board.id,
        member_user_id=membership.user_id,
        role=membership.role,
    )
    membership.delete()
    messages.success(request, "Board member removed.")
    return redirect(board)


@login_required
@require_POST
def create_list(request, board_id):
    board = _get_board_for_user(board_id, request.user)
    form = BoardListForm(request.POST)
    if form.is_valid():
        board_list = form.save(commit=False)
        board_list.board = board
        board_list.position = _next_position(board.lists)
        board_list.save()
        messages.success(request, "List created.")
    else:
        messages.error(request, "List title is required.")
    return redirect(board)


@login_required
@require_POST
def update_list(request, list_id):
    board_list = _get_list_for_user(list_id, request.user)
    if not _user_can_manage_board(board_list.board, request.user):
        return HttpResponseForbidden("Only board managers can update lists.")
    form = BoardListForm(request.POST, instance=board_list)
    if form.is_valid():
        form.save()
        messages.success(request, "List updated.")
    else:
        messages.error(request, "List title is required.")
    return redirect(board_list.board)


@login_required
@require_POST
def delete_list(request, list_id):
    board_list = _get_list_for_user(list_id, request.user)
    board = board_list.board
    if not _user_can_manage_board(board, request.user):
        return HttpResponseForbidden("Only board managers can delete lists.")
    board_list.delete()
    messages.success(request, "List deleted.")
    return redirect(board)


@login_required
@require_POST
def create_card(request, list_id):
    board_list = _get_list_for_user(list_id, request.user)
    form = CardForm(request.POST)
    if form.is_valid():
        card = form.save(commit=False)
        card.board_list = board_list
        card.created_by = request.user
        card.position = _next_position(board_list.cards)
        card.save()
        messages.success(request, "Card created.")
    else:
        messages.error(request, "Card title is required.")
    return redirect(board_list.board)


@login_required
def card_detail(request, card_id):
    card = _get_card_for_user(card_id, request.user)
    board = card.board
    if request.method == "POST":
        form = CardUpdateForm(request.POST, instance=card, board=board)
        if form.is_valid():
            form.save()
            messages.success(request, "Card updated.")
            return redirect(card)
    else:
        form = CardUpdateForm(instance=card, board=board)

    return render(
        request,
        "boards/card_detail.html",
        {
            "board": board,
            "card": card,
            "form": form,
            "comment_form": CommentForm(),
            "checklist_form": ChecklistForm(),
            "checklist_item_form": ChecklistItemForm(),
            "checklist_item_update_form": ChecklistItemUpdateForm(),
            "attachment_form": AttachmentForm(),
        },
    )


@login_required
@require_POST
def delete_card(request, card_id):
    card = _get_card_for_user(card_id, request.user)
    board = card.board
    card.delete()
    messages.success(request, "Card deleted.")
    return redirect(board)


@login_required
@require_POST
@transaction.atomic
def move_card(request, card_id):
    card = _get_card_for_user(card_id, request.user)
    try:
        payload = json.loads(request.body.decode("utf-8"))
        target_list_id = int(payload["list_id"])
        position = int(payload.get("position", 0))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid move payload."}, status=400)

    target_list = _get_list_for_user(target_list_id, request.user)
    if target_list.board_id != card.board.id:
        return JsonResponse({"error": "Cards can only move within the same board."}, status=400)

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
    return JsonResponse({"status": "ok", "card_id": card.id, "list_id": target_list.id, "position": position})


@login_required
@require_POST
def add_comment(request, card_id):
    card = _get_card_for_user(card_id, request.user)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.card = card
        comment.author = request.user
        comment.save()
        messages.success(request, "Comment added.")
    else:
        messages.error(request, "Comment cannot be empty.")
    return redirect(card)


@login_required
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment.objects.select_related("card"), pk=comment_id)
    card = _get_card_for_user(comment.card_id, request.user)
    if comment.author_id != request.user.id and not _user_can_manage_board(card.board, request.user):
        return HttpResponseForbidden("Only the comment author or a board manager can delete this comment.")
    comment.delete()
    messages.success(request, "Comment deleted.")
    return redirect(card)


@login_required
@require_POST
def add_checklist(request, card_id):
    card = _get_card_for_user(card_id, request.user)
    form = ChecklistForm(request.POST)
    if form.is_valid():
        checklist = form.save(commit=False)
        checklist.card = card
        checklist.position = _next_position(card.checklists)
        checklist.save()
        messages.success(request, "Checklist added.")
    else:
        messages.error(request, "Checklist title is required.")
    return redirect(card)


@login_required
@require_POST
def add_checklist_item(request, checklist_id):
    checklist = get_object_or_404(Checklist, pk=checklist_id)
    card = _get_card_for_user(checklist.card_id, request.user)
    form = ChecklistItemForm(request.POST)
    if form.is_valid():
        item = form.save(commit=False)
        item.checklist = checklist
        item.position = _next_position(checklist.items)
        item.save()
        messages.success(request, "Checklist item added.")
    else:
        messages.error(request, "Checklist item text is required.")
    return redirect(card)


@login_required
@require_POST
def update_checklist_item(request, item_id):
    item = get_object_or_404(ChecklistItem.objects.select_related("checklist", "checklist__card"), pk=item_id)
    card = _get_card_for_user(item.checklist.card_id, request.user)
    form = ChecklistItemUpdateForm(request.POST, instance=item)
    if form.is_valid():
        updated = form.save(commit=False)
        siblings = list(item.checklist.items.exclude(pk=item.pk).order_by("position", "created_at"))
        position = max(0, min(updated.position, len(siblings)))
        siblings.insert(position, updated)
        updated.save()
        for index, sibling in enumerate(siblings):
            if sibling.position != index:
                ChecklistItem.objects.filter(pk=sibling.pk).update(position=index)
        messages.success(request, "Checklist item updated.")
    else:
        messages.error(request, "Checklist item text is required.")
    return redirect(card)


@login_required
@require_POST
def toggle_checklist_item(request, item_id):
    item = get_object_or_404(ChecklistItem.objects.select_related("checklist", "checklist__card"), pk=item_id)
    card = _get_card_for_user(item.checklist.card_id, request.user)
    item.is_done = not item.is_done
    item.save(update_fields=["is_done"])
    return redirect(card)


@login_required
@require_POST
def delete_checklist_item(request, item_id):
    item = get_object_or_404(ChecklistItem.objects.select_related("checklist", "checklist__card"), pk=item_id)
    checklist = item.checklist
    card = _get_card_for_user(checklist.card_id, request.user)
    item.delete()
    _normalize_checklist_items(checklist)
    messages.success(request, "Checklist item deleted.")
    return redirect(card)


@login_required
@require_POST
@rate_limit("attachment_upload", "EASY_UPLOAD_RATE_LIMIT")
def add_attachment(request, card_id):
    card = _get_card_for_user(card_id, request.user)
    form = AttachmentForm(request.POST, request.FILES)
    if form.is_valid():
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
        messages.success(request, "Attachment uploaded.")
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect(card)


@login_required
@require_POST
def delete_attachment(request, attachment_id):
    attachment = get_object_or_404(Attachment.objects.select_related("card"), pk=attachment_id)
    card = _get_card_for_user(attachment.card_id, request.user)
    if attachment.uploaded_by_id != request.user.id and not _user_can_manage_board(card.board, request.user):
        return HttpResponseForbidden("Only the uploader or a board manager can delete this attachment.")
    audit_event(
        "attachment.deleted",
        request=request,
        card_id=card.id,
        attachment_id=attachment.id,
        content_type=attachment.content_type,
        size=attachment.size,
    )
    attachment.file.delete(save=False)
    attachment.delete()
    messages.success(request, "Attachment deleted.")
    return redirect(card)


@login_required
@require_GET
def download_attachment(request, attachment_id):
    attachment = get_object_or_404(Attachment.objects.select_related("card"), pk=attachment_id)
    _get_card_for_user(attachment.card_id, request.user)
    return FileResponse(
        attachment.file.open("rb"),
        as_attachment=False,
        filename=attachment.original_name,
        content_type=attachment.content_type,
    )
