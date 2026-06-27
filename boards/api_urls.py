from django.urls import path

from . import api

app_name = "api"

urlpatterns = [
    path("", api.api_root, name="root"),
    path("openapi.json", api.openapi_schema, name="openapi"),
    path("me", api.me, name="me"),
    path("boards", api.boards, name="boards"),
    path("boards/<int:board_id>", api.board_detail, name="board_detail"),
    path("boards/<int:board_id>/lists", api.board_lists, name="board_lists"),
    path("boards/<int:board_id>/members", api.board_members, name="board_members"),
    path("lists/<int:list_id>/cards", api.list_cards, name="list_cards"),
    path("cards/<int:card_id>", api.card_detail, name="card_detail"),
    path("cards/<int:card_id>/move", api.move_card, name="move_card"),
    path("cards/<int:card_id>/comments", api.card_comments, name="card_comments"),
    path("cards/<int:card_id>/checklists", api.card_checklists, name="card_checklists"),
    path("cards/<int:card_id>/attachments", api.card_attachments, name="card_attachments"),
    path("attachments/<int:attachment_id>", api.attachment_detail, name="attachment_detail"),
    path("attachments/<int:attachment_id>/download", api.attachment_download, name="attachment_download"),
    path("checklists/<int:checklist_id>", api.checklist_detail, name="checklist_detail"),
    path("checklists/<int:checklist_id>/items", api.checklist_items, name="checklist_items"),
    path("checklist-items/<int:item_id>", api.checklist_item_detail, name="checklist_item_detail"),
    path("checklist-items/<int:item_id>/toggle", api.toggle_checklist_item, name="toggle_checklist_item"),
]
