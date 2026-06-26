import { currentUser, listBoards } from "./api.js";

const status = document.querySelector("#status");
const boards = document.querySelector("#boards");
const refresh = document.querySelector("#refresh");

function setStatus(message) {
  status.textContent = message;
}

function renderBoards(items) {
  boards.replaceChildren(
    ...items.map((board) => {
      const article = document.createElement("article");
      const title = document.createElement("h2");
      const meta = document.createElement("p");
      title.textContent = board.name;
      meta.textContent = `${board.listCount ?? 0} lists | owner ${board.owner.email || board.owner.username}`;
      article.append(title, meta);
      return article;
    }),
  );
}

async function load() {
  try {
    setStatus("Loading...");
    const [{ user }, { boards: boardItems }] = await Promise.all([currentUser(), listBoards()]);
    setStatus(`Signed in as ${user.email || user.username}`);
    renderBoards(boardItems);
  } catch (error) {
    setStatus(error.message);
    boards.replaceChildren();
  }
}

refresh.addEventListener("click", load);
load();
