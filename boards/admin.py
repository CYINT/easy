from django.contrib import admin

from .models import AgentToken, Attachment, Board, BoardList, BoardMembership, Card, Checklist, ChecklistItem, Comment, Invitation


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


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["email", "code", "is_active", "used_by", "used_at", "created_by", "created_at"]
    list_filter = ["is_active", "used_at", "created_at"]
    search_fields = ["email", "code", "used_by__email", "created_by__email"]
    readonly_fields = ["code", "used_by", "used_at", "created_at"]

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(AgentToken)
class AgentTokenAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "token_prefix", "is_active", "expires_at", "last_used_at", "created_at"]
    list_filter = ["is_active", "expires_at", "created_at"]
    search_fields = ["name", "user__email", "user__username", "token_prefix"]
    readonly_fields = ["token_hash", "token_prefix", "last_used_at", "created_at"]
