function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
  return "";
}

function getCsrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || getCookie("csrftoken");
}

function cardPosition(card) {
  const stack = card.closest("[data-dropzone]");
  return Array.from(stack.querySelectorAll("[data-card-id]")).indexOf(card);
}

function nearestCard(stack, y) {
  const cards = Array.from(stack.querySelectorAll("[data-card-id]:not(.dragging)"));
  return cards.reduce(
    (closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closest.offset) return { offset, element: child };
      return closest;
    },
    { offset: Number.NEGATIVE_INFINITY, element: null },
  ).element;
}

async function persistMove(card) {
  const stack = card.closest("[data-dropzone]");
  const response = await fetch(card.dataset.moveUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify({ list_id: stack.dataset.listId, position: cardPosition(card) }),
  });
  if (!response.ok) throw new Error("Move failed");
}

document.addEventListener("DOMContentLoaded", () => {
  let dragged = null;
  let origin = null;
  let originNext = null;
  let didDrop = false;
  let suppressClick = false;

  function rememberOrigin(card) {
    origin = card.parentElement;
    originNext = card.nextElementSibling;
  }

  function restoreOrigin(card) {
    if (!origin) return;
    if (originNext && originNext.parentElement === origin) origin.insertBefore(card, originNext);
    else origin.appendChild(card);
  }

  function clearDropTargets() {
    document.querySelectorAll(".drop-target").forEach((target) => target.classList.remove("drop-target"));
  }

  function placeCard(stack, clientY) {
    if (!dragged || dragged.parentElement === stack && stack.children.length === 1) return;
    const before = nearestCard(stack, clientY);
    if (before) stack.insertBefore(dragged, before);
    else stack.appendChild(dragged);
  }

  async function saveDraggedMove() {
    if (!dragged) return;
    try {
      await persistMove(dragged);
    } catch (error) {
      restoreOrigin(dragged);
      window.alert("Easy could not save that move. The card was returned to its previous list.");
    }
  }

  function resetDrag() {
    if (dragged) dragged.classList.remove("dragging");
    document.body.classList.remove("is-dragging-card");
    clearDropTargets();
    dragged = null;
    origin = null;
    originNext = null;
    didDrop = false;
  }

  function siblingList(stack, direction) {
    const lists = Array.from(document.querySelectorAll("[data-dropzone]"));
    const current = lists.indexOf(stack);
    if (current < 0) return null;
    return lists[current + direction] || null;
  }

  async function moveWithKeyboard(card, direction) {
    rememberOrigin(card);
    const stack = card.closest("[data-dropzone]");
    if (direction === "up") {
      const previous = card.previousElementSibling;
      if (previous) stack.insertBefore(card, previous);
    } else if (direction === "down") {
      const next = card.nextElementSibling;
      if (next) stack.insertBefore(next, card);
    } else if (direction === "left" || direction === "right") {
      const target = siblingList(stack, direction === "left" ? -1 : 1);
      if (target) target.appendChild(card);
    }

    try {
      await persistMove(card);
      card.focus();
    } catch (error) {
      restoreOrigin(card);
      window.alert("Easy could not save that move. The card was returned to its previous list.");
    } finally {
      origin = null;
      originNext = null;
    }
  }

  document.querySelectorAll("[data-card-id]").forEach((card) => {
    card.addEventListener("dragstart", (event) => {
      dragged = card;
      rememberOrigin(card);
      didDrop = false;
      suppressClick = false;
      document.body.classList.add("is-dragging-card");
      card.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", card.dataset.cardId);
    });

    card.addEventListener("dragend", () => {
      if (!dragged) return;
      if (!didDrop) {
        restoreOrigin(dragged);
      }
      suppressClick = true;
      resetDrag();
      window.setTimeout(() => {
        suppressClick = false;
      }, 0);
    });

    card.addEventListener("click", (event) => {
      if (!suppressClick) return;
      event.preventDefault();
    });

    card.addEventListener("keydown", (event) => {
      if (!event.altKey) return;
      const keys = {
        ArrowUp: "up",
        ArrowDown: "down",
        ArrowLeft: "left",
        ArrowRight: "right",
      };
      const direction = keys[event.key];
      if (!direction) return;
      event.preventDefault();
      moveWithKeyboard(card, direction);
    });
  });

  document.querySelectorAll("[data-dropzone]").forEach((stack) => {
    stack.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (!dragged) return;
      event.dataTransfer.dropEffect = "move";
      stack.classList.add("drop-target");
      placeCard(stack, event.clientY);
    });

    stack.addEventListener("dragenter", () => stack.classList.add("drop-target"));
    stack.addEventListener("dragleave", (event) => {
      if (!stack.contains(event.relatedTarget)) stack.classList.remove("drop-target");
    });
    stack.addEventListener("drop", async (event) => {
      event.preventDefault();
      if (!dragged) return;
      didDrop = true;
      placeCard(stack, event.clientY);
      await saveDraggedMove();
      suppressClick = true;
      resetDrag();
      window.setTimeout(() => {
        suppressClick = false;
      }, 0);
    });
  });
});
