# Easy Agent API

Easy exposes a session-authenticated JSON API under `/api/v1/`. This API is the contract agents and standalone frontends should use. The Django template UI is compatibility surface, not the integration boundary.

## Authentication

- Browser clients use the Django `sessionid` cookie.
- Unsafe requests must include `X-CSRFToken`.
- Invite-only signup, login, MFA, password reset, and administrator bootstrap are still handled by django-allauth and Django admin.

Programmatic agents should authenticate through an approved session or a future API-token flow. Do not scrape Django templates.

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

## Collaboration

- `POST /api/v1/boards/{boardId}/members` with `{ "email": "user@example.com", "role": "member" }`
- `POST /api/v1/cards/{cardId}/comments` with `{ "body": "..." }`

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
