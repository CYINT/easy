const API_BASE = window.EASY_API_BASE || "/api/v1";

function csrfToken() {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="))
    ?.split("=")[1] || "";
}

export async function apiFetch(path, options = {}) {
  const headers = {
    Accept: "application/json",
    ...options.headers,
  };
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const token = csrfToken();
  if (token) {
    headers["X-CSRFToken"] = token;
  }
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...options,
    headers,
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const message = payload.error?.message || `Easy API request failed with ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

export function currentUser() {
  return apiFetch("/me");
}

export function listBoards() {
  return apiFetch("/boards");
}

export function getBoard(boardId) {
  return apiFetch(`/boards/${boardId}`);
}

export function createBoard(data) {
  return apiFetch("/boards", { method: "POST", body: JSON.stringify(data) });
}

export function createList(boardId, data) {
  return apiFetch(`/boards/${boardId}/lists`, { method: "POST", body: JSON.stringify(data) });
}

export function addBoardMember(boardId, data) {
  return apiFetch(`/boards/${boardId}/members`, { method: "POST", body: JSON.stringify(data) });
}

export function updateMembership(membershipId, data) {
  return apiFetch(`/memberships/${membershipId}`, { method: "PATCH", body: JSON.stringify(data) });
}

export function deleteMembership(membershipId) {
  return apiFetch(`/memberships/${membershipId}`, { method: "DELETE" });
}

export function createCard(listId, data) {
  return apiFetch(`/lists/${listId}/cards`, { method: "POST", body: JSON.stringify(data) });
}

export function updateCard(cardId, data) {
  return apiFetch(`/cards/${cardId}`, { method: "PATCH", body: JSON.stringify(data) });
}

export function moveCard(cardId, data) {
  return apiFetch(`/cards/${cardId}/move`, { method: "POST", body: JSON.stringify(data) });
}

export function createComment(cardId, data) {
  return apiFetch(`/cards/${cardId}/comments`, { method: "POST", body: JSON.stringify(data) });
}

export function deleteComment(commentId) {
  return apiFetch(`/comments/${commentId}`, { method: "DELETE" });
}

export function createChecklist(cardId, data) {
  return apiFetch(`/cards/${cardId}/checklists`, { method: "POST", body: JSON.stringify(data) });
}

export function createChecklistItem(checklistId, data) {
  return apiFetch(`/checklists/${checklistId}/items`, { method: "POST", body: JSON.stringify(data) });
}

export function toggleChecklistItem(itemId) {
  return apiFetch(`/checklist-items/${itemId}/toggle`, { method: "POST", body: JSON.stringify({}) });
}

export function uploadAttachment(cardId, file) {
  const body = new FormData();
  body.append("file", file);
  return apiFetch(`/cards/${cardId}/attachments`, { method: "POST", body });
}
