OPENAPI_SCHEMA = {
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
