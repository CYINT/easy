# Easy Agent API

Easy exposes a session-authenticated JSON API under `/api/v1/`. This API is the contract agents and standalone frontends should use. The Django template UI is compatibility surface, not the integration boundary.

## Authentication

- Programmatic agents should use an `Authorization: Bearer <token>` header.
- Browser clients may use the Django `sessionid` cookie.
- Unsafe browser-session requests must include `X-CSRFToken`.
- Invite-only signup, login, MFA, password reset, and administrator bootstrap are still handled by django-allauth and Django admin.

Create a read-only token for an existing active user with:

```powershell
.\.venv\Scripts\python.exe manage.py create_agent_token user@example.com --name local-agent
```

Create a write-capable token only when an agent needs to mutate boards:

```powershell
.\.venv\Scripts\python.exe manage.py create_agent_token user@example.com --name local-agent --scope write
```

The raw token is shown once. Easy stores only a SHA-256 hash and a short prefix. Revoke tokens from Django admin by setting `is_active` to false. Do not scrape Django templates.

Token scopes:

- `read`: safe `GET` API requests only.
- `write`: read plus mutation requests, still limited by the owning user's board permissions.

## Discovery

- `GET /api/v1/` returns service links.
- `GET /api/v1/openapi.json` returns a compact OpenAPI schema.
- `GET /api/v1/me` returns the current user.

## Boards

- `GET /api/v1/boards`
- `POST /api/v1/boards` with `{ "name": "...", "description": "..." }`
- `GET /api/v1/boards/{boardId}`
- `PATCH /api/v1/boards/{boardId}`
- `DELETE /api/v1/boards/{boardId}`

## Lists And Cards

- `POST /api/v1/boards/{boardId}/lists` with `{ "title": "..." }`
- `POST /api/v1/lists/{listId}/cards` with `{ "title": "...", "description": "..." }`
- `GET /api/v1/cards/{cardId}`
- `PATCH /api/v1/cards/{cardId}` with `{ "title": "...", "description": "...", "assigneeIds": [] }`
- `DELETE /api/v1/cards/{cardId}`
- `POST /api/v1/cards/{cardId}/move` with `{ "listId": 123, "position": 0 }`

## Checklists

Card and board-detail payloads include nested `checklists` and `items`.

- `POST /api/v1/cards/{cardId}/checklists` with `{ "title": "..." }`
- `PATCH /api/v1/checklists/{checklistId}` with `{ "title": "..." }`
- `DELETE /api/v1/checklists/{checklistId}`
- `POST /api/v1/checklists/{checklistId}/items` with `{ "text": "..." }`
- `PATCH /api/v1/checklist-items/{itemId}` with `{ "text": "...", "position": 0, "isDone": true }`
- `DELETE /api/v1/checklist-items/{itemId}`
- `POST /api/v1/checklist-items/{itemId}/toggle`

## Collaboration

- `POST /api/v1/boards/{boardId}/members` with `{ "email": "user@example.com", "role": "member" }`
- `POST /api/v1/cards/{cardId}/comments` with `{ "body": "..." }`

## Attachments

Card and board-detail payloads include nested attachment metadata. Uploads use multipart form data with a `file` field and are subject to the same size, type, permission, audit, and rate-limit controls as the browser UI.

- `POST /api/v1/cards/{cardId}/attachments` with multipart field `file`
- `GET /api/v1/attachments/{attachmentId}`
- `GET /api/v1/attachments/{attachmentId}/download`
- `DELETE /api/v1/attachments/{attachmentId}`

## Response Shape

Successful responses wrap resources by type, for example:

```json
{ "board": { "id": 1, "name": "Launch" } }
```

Errors use:

```json
{ "error": { "code": "validation_error", "message": "Board name is required." } }
```

## Frontend Boundary

The standalone frontend shell is in `frontend/`. It imports only `frontend/src/api.js`, which calls `/api/v1/`. New UI work should go there instead of adding behavior to Django templates.
