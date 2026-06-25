# Easy Core Workflow API

Easy's MVP uses server-rendered Django views with form posts for write operations and one JSON endpoint for drag/drop card ordering. All routes require an authenticated user except the home, account, and health routes.

## Boards

- `GET /boards/` lists boards visible to the current user and shows the board creation form.
- `POST /boards/` creates a board owned by the current user.
- `GET /boards/<board_id>/` shows board lists, cards, members, and board settings.
- `POST /boards/<board_id>/update/` updates the board name and description. The user must be the board owner or an admin member.
- `POST /boards/<board_id>/delete/` deletes the board. The user must be the board owner.
- `POST /boards/<board_id>/members/` adds or updates a board member by email. The user must be the board owner or an admin member.
- `POST /memberships/<membership_id>/remove/` removes a board member. The user must be the board owner or an admin member.

## Lists

- `POST /boards/<board_id>/lists/` creates a list at the end of a board.
- `POST /lists/<list_id>/update/` renames a list. The user must be the board owner or an admin member.
- `POST /lists/<list_id>/delete/` deletes a list and its cards. The user must be the board owner or an admin member.

## Cards

- `POST /lists/<list_id>/cards/` creates a card at the end of a list.
- `GET /cards/<card_id>/` shows card details, comments, checklists, assignments, and attachments.
- `POST /cards/<card_id>/` updates card title, description, and assignees.
- `POST /cards/<card_id>/delete/` deletes a card.
- `POST /cards/<card_id>/move/` accepts JSON `{ "list_id": <target_list_id>, "position": <zero_based_position> }` and persists drag/drop card ordering. The target list must be on the same board.

## Comments

- `POST /cards/<card_id>/comments/` adds a comment.
- `POST /comments/<comment_id>/delete/` deletes a comment. The user must be the comment author, board owner, or an admin member.

## Checklists

- `POST /cards/<card_id>/checklists/` adds a checklist.
- `POST /checklists/<checklist_id>/items/` adds a checklist item at the end of the checklist.
- `POST /checklist-items/<item_id>/update/` updates checklist item text and zero-based position, then normalizes sibling positions.
- `POST /checklist-items/<item_id>/toggle/` toggles completion.
- `POST /checklist-items/<item_id>/delete/` deletes an item and normalizes sibling positions.

## Attachments

- `POST /cards/<card_id>/attachments/` uploads an attachment after validating content type and size.
- `GET /attachments/<attachment_id>/download/` streams an attachment through a permission-checked endpoint.
- `POST /attachments/<attachment_id>/delete/` deletes an attachment. The user must be the uploader, board owner, or an admin member.

## Permission Model

Board owners have full access. Board admin members can manage board metadata, members, lists, comments, and attachments. Board members can view the board and work with cards, comments, checklists, and attachments. Non-members receive `404` for board/card resources so private board existence is not exposed.
