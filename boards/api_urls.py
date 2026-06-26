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
]
