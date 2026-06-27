import {
  addBoardMember,
  createBoard,
  createCard,
  createChecklist,
  createChecklistItem,
  createComment,
  createList,
  currentUser,
  deleteComment,
  getBoard,
  listBoards,
  moveCard,
  toggleChecklistItem,
  updateCard,
  uploadAttachment,
} from "./api.js";

const state = {
  user: null,
  boards: [],
  board: null,
  selectedCardId: null,
  loading: false,
};

const app = document.querySelector("#app");
const status = document.querySelector("#status");

function setStatus(message) {
  status.textContent = message;
}

function el(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(options)) {
    if (key === "className") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "html") node.innerHTML = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  for (const child of children) node.append(child);
  return node;
}

function selectedCard() {
  for (const list of state.board?.lists ?? []) {
    const card = list.cards.find((item) => item.id === state.selectedCardId);
    if (card) return card;
  }
  return null;
}

async function run(action, successMessage) {
  try {
    state.loading = true;
    render();
    await action();
    if (successMessage) setStatus(successMessage);
  } catch (error) {
    setStatus(error.message);
  } finally {
    state.loading = false;
    render();
  }
}

async function refreshBoards() {
  const [{ user }, { boards }] = await Promise.all([currentUser(), listBoards()]);
  state.user = user;
  state.boards = boards;
  if (!state.board && boards.length) {
    await loadBoard(boards[0].id);
  }
}

async function loadBoard(boardId) {
  const { board } = await getBoard(boardId);
  state.board = board;
  if (!selectedCard()) {
    state.selectedCardId = board.lists[0]?.cards[0]?.id ?? null;
  }
}

function form(placeholder, buttonText, onSubmit) {
  const input = el("input", { placeholder, "aria-label": placeholder });
  return el("form", {
    className: "inline-form",
    onsubmit: (event) => {
      event.preventDefault();
      const value = input.value.trim();
      if (!value) return;
      input.value = "";
      onSubmit(value);
    },
  }, [input, el("button", { type: "submit", text: buttonText })]);
}

function boardUsers() {
  if (!state.board) return [];
  return [state.board.owner, ...(state.board.members ?? []).map((membership) => membership.user)];
}

function userLabel(user) {
  return user.email || user.username;
}

function renderSidebar() {
  return el("aside", { className: "sidebar" }, [
    el("div", { className: "brand", text: "Easy" }),
    el("div", { className: "user", text: state.user ? state.user.email || state.user.username : "Not signed in" }),
    form("New board", "Create", (name) => run(async () => {
      const { board } = await createBoard({ name });
      await refreshBoards();
      await loadBoard(board.id);
    }, "Board created.")),
    el("nav", { className: "board-list", "aria-label": "Boards" }, state.boards.map((board) => (
      el("button", {
        type: "button",
        className: board.id === state.board?.id ? "board-link active" : "board-link",
        text: board.name,
        onclick: () => run(() => loadBoard(board.id)),
      })
    ))),
  ]);
}

function renderBoard() {
  if (!state.board) {
    return el("section", { className: "empty", text: "Create a board to start planning." });
  }
  return el("section", { className: "workspace" }, [
    el("header", { className: "workspace-header" }, [
      el("div", {}, [
        el("h1", { text: state.board.name }),
        el("p", { text: state.board.description || "No description" }),
      ]),
      el("div", { className: "workspace-tools" }, [
        form("New list", "Add list", (title) => run(async () => {
          await createList(state.board.id, { title });
          await loadBoard(state.board.id);
        }, "List added.")),
        renderMemberForm(),
      ]),
    ]),
    renderMembers(),
    el("div", { className: "lists" }, state.board.lists.map(renderList)),
  ]);
}

function renderMemberForm() {
  const email = el("input", { type: "email", placeholder: "Member email", "aria-label": "Member email" });
  const role = el("select", { "aria-label": "Member role" }, [
    el("option", { value: "member", text: "Member" }),
    el("option", { value: "admin", text: "Admin" }),
  ]);
  return el("form", {
    className: "inline-form member-form",
    onsubmit: (event) => {
      event.preventDefault();
      const value = email.value.trim();
      if (!value) return;
      email.value = "";
      run(async () => {
        await addBoardMember(state.board.id, { email: value, role: role.value });
        await loadBoard(state.board.id);
      }, "Member saved.");
    },
  }, [email, role, el("button", { type: "submit", text: "Add member" })]);
}

function renderMembers() {
  return el("div", { className: "members", "aria-label": "Board members" }, [
    el("span", { text: `Owner: ${userLabel(state.board.owner)}` }),
    ...(state.board.members ?? []).map((membership) => (
      el("span", { text: `${userLabel(membership.user)} (${membership.role})` })
    )),
  ]);
}

function renderList(list, index) {
  return el("section", { className: "lane" }, [
    el("header", { className: "lane-header" }, [
      el("h2", { text: list.title }),
      el("span", { text: `${list.cards.length}` }),
    ]),
    el("div", { className: "cards" }, list.cards.map((card, cardIndex) => renderCard(card, list, index, cardIndex))),
    form("New card", "Add card", (title) => run(async () => {
      await createCard(list.id, { title });
      await loadBoard(state.board.id);
    }, "Card added.")),
  ]);
}

function renderCard(card, list, listIndex, cardIndex) {
  const checklistTotal = card.checklists.reduce((total, checklist) => total + checklist.items.length, 0);
  const checklistDone = card.checklists.reduce((total, checklist) => total + checklist.items.filter((item) => item.isDone).length, 0);
  return el("article", {
    className: card.id === state.selectedCardId ? "card selected" : "card",
    onclick: () => {
      state.selectedCardId = card.id;
      render();
    },
  }, [
    el("h3", { text: card.title }),
    el("p", { text: card.description || "No description" }),
    el("div", { className: "card-meta" }, [
      el("span", { text: `${checklistDone}/${checklistTotal} checks` }),
      el("span", { text: `${card.attachments.length} files` }),
      el("span", { text: `${card.assignees.length} assigned` }),
    ]),
    el("div", { className: "card-actions" }, [
      el("button", {
        type: "button",
        text: "<",
        disabled: listIndex === 0 ? "disabled" : null,
        onclick: (event) => {
          event.stopPropagation();
          const target = state.board.lists[listIndex - 1];
          run(async () => {
            await moveCard(card.id, { listId: target.id, position: target.cards.length });
            await loadBoard(state.board.id);
          }, "Card moved.");
        },
      }),
      el("button", {
        type: "button",
        text: "^",
        disabled: cardIndex === 0 ? "disabled" : null,
        onclick: (event) => {
          event.stopPropagation();
          run(async () => {
            await moveCard(card.id, { listId: list.id, position: cardIndex - 1 });
            await loadBoard(state.board.id);
          }, "Card reordered.");
        },
      }),
      el("button", {
        type: "button",
        text: "v",
        disabled: cardIndex >= list.cards.length - 1 ? "disabled" : null,
        onclick: (event) => {
          event.stopPropagation();
          run(async () => {
            await moveCard(card.id, { listId: list.id, position: cardIndex + 1 });
            await loadBoard(state.board.id);
          }, "Card reordered.");
        },
      }),
      el("button", {
        type: "button",
        text: ">",
        disabled: listIndex >= state.board.lists.length - 1 ? "disabled" : null,
        onclick: (event) => {
          event.stopPropagation();
          const target = state.board.lists[listIndex + 1];
          run(async () => {
            await moveCard(card.id, { listId: target.id, position: target.cards.length });
            await loadBoard(state.board.id);
          }, "Card moved.");
        },
      }),
    ]),
  ]);
}

function renderDetail() {
  const card = selectedCard();
  if (!card) return el("aside", { className: "detail empty", text: "Select a card." });
  return el("aside", { className: "detail" }, [
    el("h2", { text: card.title }),
    el("p", { text: card.description || "No description" }),
    el("section", {}, [
      el("h3", { text: "Assignees" }),
      renderAssigneeForm(card),
    ]),
    el("section", {}, [
      el("h3", { text: "Comments" }),
      el("ul", { className: "comments" }, card.comments.map(renderComment)),
      form("Add a comment", "Comment", (body) => run(async () => {
        await createComment(card.id, { body });
        await loadBoard(state.board.id);
      }, "Comment added.")),
    ]),
    el("section", {}, [
      el("h3", { text: "Checklists" }),
      ...card.checklists.map(renderChecklist),
      form("Checklist title", "Add checklist", (title) => run(async () => {
        await createChecklist(card.id, { title });
        await loadBoard(state.board.id);
      }, "Checklist added.")),
    ]),
    el("section", {}, [
      el("h3", { text: "Attachments" }),
      el("ul", { className: "attachments" }, card.attachments.map((attachment) => (
        el("li", {}, [
          el("a", { href: attachment.downloadUrl, target: "_blank", text: attachment.originalName }),
          el("span", { text: `${Math.ceil(attachment.size / 1024)} KB` }),
        ])
      ))),
      renderAttachmentForm(card),
    ]),
  ]);
}

function renderAssigneeForm(card) {
  const selectedIds = new Set(card.assignees.map((user) => String(user.id)));
  const users = boardUsers();
  if (!users.length) return el("p", { text: "No board users." });
  return el("form", {
    className: "assignee-form",
    onsubmit: (event) => {
      event.preventDefault();
      const assigneeIds = Array.from(event.currentTarget.querySelectorAll("input:checked")).map((input) => input.value);
      run(async () => {
        await updateCard(card.id, { assigneeIds });
        await loadBoard(state.board.id);
      }, "Assignees saved.");
    },
  }, [
    el("div", { className: "assignee-options" }, users.map((user) => (
      el("label", {}, [
        el("input", {
          type: "checkbox",
          value: user.id,
          checked: selectedIds.has(String(user.id)) ? "checked" : null,
        }),
        el("span", { text: userLabel(user) }),
      ])
    ))),
    el("button", { type: "submit", text: "Save assignees" }),
  ]);
}

function renderComment(comment) {
  return el("li", {}, [
    el("div", {}, [
      el("strong", { text: comment.author.email || comment.author.username }),
      el("p", { text: comment.body }),
    ]),
    el("button", {
      type: "button",
      text: "Delete",
      onclick: () => run(async () => {
        await deleteComment(comment.id);
        await loadBoard(state.board.id);
      }, "Comment deleted."),
    }),
  ]);
}

function renderChecklist(checklist) {
  return el("div", { className: "checklist" }, [
    el("h4", { text: checklist.title }),
    el("ul", {}, checklist.items.map((item) => (
      el("li", {}, [
        el("button", {
          type: "button",
          className: item.isDone ? "check done" : "check",
          text: item.isDone ? "x" : "",
          onclick: () => run(async () => {
            await toggleChecklistItem(item.id);
            await loadBoard(state.board.id);
          }),
        }),
        el("span", { className: item.isDone ? "done-text" : "", text: item.text }),
      ])
    ))),
    form("Checklist item", "Add item", (text) => run(async () => {
      await createChecklistItem(checklist.id, { text });
      await loadBoard(state.board.id);
    }, "Checklist item added.")),
  ]);
}

function renderAttachmentForm(card) {
  const input = el("input", { type: "file", name: "file", "aria-label": "Attachment file" });
  return el("form", {
    className: "inline-form",
    onsubmit: (event) => {
      event.preventDefault();
      const file = input.files[0];
      if (!file) return;
      input.value = "";
      run(async () => {
        await uploadAttachment(card.id, file);
        await loadBoard(state.board.id);
      }, "Attachment uploaded.");
    },
  }, [input, el("button", { type: "submit", text: "Upload" })]);
}

function render() {
  app.replaceChildren(renderSidebar(), renderBoard(), renderDetail());
  document.body.toggleAttribute("aria-busy", state.loading);
}

async function start() {
  setStatus("Loading...");
  await run(async () => {
    await refreshBoards();
  }, "Ready.");
}

start();
