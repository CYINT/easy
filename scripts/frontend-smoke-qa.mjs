import { spawn } from "node:child_process";
import { once } from "node:events";

import { chromium } from "playwright";

const PORT = Number(process.env.EASY_FRONTEND_QA_PORT || 5173);
const ORIGIN = `http://127.0.0.1:${PORT}`;

const board = {
  id: 1,
  name: "Release board",
  description: "Frontend QA board",
  owner: { id: 1, email: "owner@example.com", username: "owner" },
  lists: [
    {
      id: 10,
      title: "Todo",
      position: 0,
      cards: [
        {
          id: 100,
          title: "Wire frontend",
          description: "Use API only",
          position: 0,
          assignees: [{ id: 2, email: "member@example.com", username: "member" }],
          createdBy: null,
          comments: [
            { id: 500, body: "Ready for review", author: { email: "owner@example.com", username: "owner" }, createdAt: "2026-06-27T00:00:00Z" },
          ],
          checklists: [
            {
              id: 200,
              title: "QA",
              position: 0,
              items: [{ id: 300, text: "Render board", isDone: false, position: 0 }],
            },
          ],
          attachments: [
            {
              id: 400,
              originalName: "spec.txt",
              contentType: "text/plain",
              size: 42,
              isImage: false,
              downloadUrl: "/api/v1/attachments/400/download",
            },
          ],
        },
      ],
    },
    { id: 11, title: "Done", position: 1, cards: [] },
  ],
  members: [
    { id: 30, role: "member", user: { id: 2, email: "member@example.com", username: "member" }, createdAt: "2026-06-27T00:00:00Z" },
  ],
};

function startServer() {
  const server = spawn("python", ["-m", "http.server", String(PORT), "-d", "frontend"], {
    stdio: ["ignore", "ignore", "pipe"],
    windowsHide: true,
  });
  server.stderr.on("data", (chunk) => process.stderr.write(chunk));
  return server;
}

async function waitForServer() {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${ORIGIN}/index.html`);
      if (response.ok) return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
  }
  throw new Error(`Frontend QA server did not start on ${ORIGIN}`);
}

async function main() {
  const server = startServer();
  try {
    await waitForServer();
    if (server.exitCode !== null) {
      throw new Error(`Frontend QA server exited early with ${server.exitCode}`);
    }

    const browser = await chromium.launch({ headless: true });
    const results = [];
    for (const viewport of [
      { width: 1280, height: 820 },
      { width: 390, height: 844 },
    ]) {
      const page = await browser.newPage({ viewport });
      await page.route("**/api/v1/me", (route) => route.fulfill({ json: { user: board.owner } }));
      await page.route("**/api/v1/boards", async (route) => {
        if (route.request().method() === "POST") {
          return route.fulfill({ status: 201, json: { board: { ...board, id: 2, name: "Created board" } } });
        }
        return route.fulfill({ json: { boards: [{ id: 1, name: board.name, owner: board.owner, listCount: 2 }] } });
      });
      await page.route("**/api/v1/boards/1", (route) => route.fulfill({ json: { board } }));
      await page.route("**/api/v1/boards/1/members", (route) => route.fulfill({ status: 200, json: { membership: board.members[0] } }));
      await page.route("**/api/v1/memberships/30", (route) => route.fulfill({ status: route.request().method() === "DELETE" ? 204 : 200, json: { membership: board.members[0] } }));
      await page.route("**/api/v1/boards/1/lists", (route) => route.fulfill({ status: 201, json: { list: { id: 12, title: "Later" } } }));
      await page.route("**/api/v1/lists/10/cards", (route) => route.fulfill({ status: 201, json: { card: { id: 101, title: "New card" } } }));
      await page.route("**/api/v1/cards/100", (route) => route.fulfill({ json: { card: board.lists[0].cards[0] } }));
      await page.route("**/api/v1/cards/100/move", (route) => route.fulfill({ json: { card: board.lists[0].cards[0] } }));
      await page.route("**/api/v1/cards/100/comments", (route) => route.fulfill({ status: 201, json: { comment: board.lists[0].cards[0].comments[0] } }));
      await page.route("**/api/v1/comments/500", (route) => route.fulfill({ status: 204, body: "" }));
      await page.route("**/api/v1/checklist-items/300/toggle", (route) => route.fulfill({ json: { item: { id: 300, isDone: true } } }));

      await page.goto(`${ORIGIN}/index.html`);
      await page.waitForSelector("text=Release board");
      await page.waitForSelector("text=Wire frontend");
      await page.waitForSelector("text=member@example.com");
      await page.waitForSelector("text=Remove");
      await page.waitForSelector("text=Ready for review");
      await page.waitForSelector("text=spec.txt");
      const metrics = await page.evaluate(() => ({
        status: document.querySelector("#status")?.textContent,
        columns: document.querySelectorAll(".lane").length,
        cards: document.querySelectorAll(".card").length,
        overflow: document.documentElement.scrollWidth > window.innerWidth,
        width: window.innerWidth,
      }));
      await page.close();
      if (metrics.status !== "Ready." || metrics.columns !== 2 || metrics.cards !== 1 || metrics.overflow) {
        throw new Error(`Unexpected frontend smoke metrics: ${JSON.stringify(metrics)}`);
      }
      results.push(metrics);
    }
    await browser.close();
    console.log(JSON.stringify(results));
  } finally {
    if (server.exitCode === null) {
      const exit = once(server, "exit").catch(() => {});
      server.kill();
      await exit;
    }
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
