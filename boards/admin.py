from django.contrib import admin

from .models import Attachment, Board, BoardList, BoardMembership, Card, Checklist, ChecklistItem, Comment


class BoardMembershipInline(admin.TabularInline):
    model = BoardMembership
    extra = 0


class BoardListInline(admin.TabularInline):
    model = BoardList
    extra = 0


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "created_at", "updated_at"]
    search_fields = ["name", "owner__email", "owner__username"]
    inlines = [BoardMembershipInline, BoardListInline]


@admin.register(BoardList)
class BoardListAdmin(admin.ModelAdmin):
    list_display = ["title", "board", "position"]
    list_filter = ["board"]


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ["title", "board_list", "position", "created_by", "updated_at"]
    list_filter = ["board_list__board"]
    search_fields = ["title", "description"]
    filter_horizontal = ["assignees"]


admin.site.register(Comment)
admin.site.register(Checklist)
admin.site.register(ChecklistItem)
admin.site.register(Attachment)
