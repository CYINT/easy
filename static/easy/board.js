function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
  return "";
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
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({ list_id: stack.dataset.listId, position: cardPosition(card) }),
  });
  if (!response.ok) throw new Error("Move failed");
}

document.addEventListener("DOMContentLoaded", () => {
  let dragged = null;
  let origin = null;

  document.querySelectorAll("[data-card-id]").forEach((card) => {
    card.addEventListener("dragstart", (event) => {
      dragged = card;
      origin = card.parentElement;
      card.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", card.dataset.cardId);
    });

    card.addEventListener("dragend", async () => {
      if (!dragged) return;
      dragged.classList.remove("dragging");
      document.querySelectorAll(".drop-target").forEach((target) => target.classList.remove("drop-target"));
      try {
        await persistMove(dragged);
      } catch (error) {
        origin.appendChild(dragged);
        window.alert("Easy could not save that move. The card was returned to its previous list.");
      } finally {
        dragged = null;
        origin = null;
      }
    });
  });

  document.querySelectorAll("[data-dropzone]").forEach((stack) => {
    stack.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (!dragged) return;
      const before = nearestCard(stack, event.clientY);
      if (before) stack.insertBefore(dragged, before);
      else stack.appendChild(dragged);
    });

    stack.addEventListener("dragenter", () => stack.classList.add("drop-target"));
    stack.addEventListener("dragleave", () => stack.classList.remove("drop-target"));
    stack.addEventListener("drop", (event) => {
      event.preventDefault();
      stack.classList.remove("drop-target");
    });
  });
});
