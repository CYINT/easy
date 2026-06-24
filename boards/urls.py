from django.urls import path

from . import views

app_name = "boards"

urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.health, name="health"),
    path("boards/", views.dashboard, name="dashboard"),
    path("boards/<int:board_id>/", views.board_detail, name="board_detail"),
    path("boards/<int:board_id>/lists/", views.create_list, name="create_list"),
    path("boards/<int:board_id>/members/", views.add_board_member, name="add_board_member"),
    path("memberships/<int:membership_id>/remove/", views.remove_board_member, name="remove_board_member"),
    path("lists/<int:list_id>/cards/", views.create_card, name="create_card"),
    path("cards/<int:card_id>/", views.card_detail, name="card_detail"),
    path("cards/<int:card_id>/move/", views.move_card, name="move_card"),
    path("cards/<int:card_id>/comments/", views.add_comment, name="add_comment"),
    path("cards/<int:card_id>/checklists/", views.add_checklist, name="add_checklist"),
    path("cards/<int:card_id>/attachments/", views.add_attachment, name="add_attachment"),
    path("attachments/<int:attachment_id>/download/", views.download_attachment, name="download_attachment"),
    path("checklists/<int:checklist_id>/items/", views.add_checklist_item, name="add_checklist_item"),
    path("checklist-items/<int:item_id>/toggle/", views.toggle_checklist_item, name="toggle_checklist_item"),
]
