import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const qaDir = path.join(root, ".easy-qa");
const dbPath = path.join(qaDir, "dragdrop.sqlite3");
const port = Number(process.env.EASY_QA_PORT || 28765);
const baseUrl = `http://127.0.0.1:${port}`;
const python = process.env.PYTHON || path.join(root, ".venv", "Scripts", "python.exe");

fs.mkdirSync(qaDir, { recursive: true });
fs.rmSync(dbPath, { force: true });

const env = {
  ...process.env,
  DJANGO_SETTINGS_MODULE: "easy_project.settings",
  DATABASE_URL: `sqlite:///${dbPath.replaceAll("\\", "/")}`,
  DJANGO_DEBUG: "true",
  DJANGO_ALLOWED_HOSTS: "127.0.0.1,localhost",
  DJANGO_CSRF_TRUSTED_ORIGINS: `http://127.0.0.1:${port}`,
  DJANGO_SECURE_SSL_REDIRECT: "false",
  DJANGO_SESSION_COOKIE_SECURE: "false",
  DJANGO_CSRF_COOKIE_SECURE: "false",
  DJANGO_CSRF_COOKIE_HTTPONLY: process.env.EASY_QA_CSRF_COOKIE_HTTPONLY || "false",
};

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: root,
    env,
    encoding: "utf8",
    stdio: options.stdio || "pipe",
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed\n${result.stdout || ""}\n${result.stderr || ""}`);
  }
  return (result.stdout || "").trim();
}

run(python, ["manage.py", "migrate", "--noinput"], { stdio: "inherit" });

const fixture = JSON.parse(
  run(python, [
    "-c",
    `
import json
import django

django.setup()

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import Client
from boards.models import Board, BoardList, Card

User = get_user_model()
user = User.objects.create_user(username="qa", email="qa@example.com", password="password-12345")
board = Board.objects.create(name="QA Board", owner=user)
todo = BoardList.objects.create(board=board, title="Todo", position=0)
done = BoardList.objects.create(board=board, title="Done", position=1)
first = Card.objects.create(board_list=todo, title="First", position=0, created_by=user)
second = Card.objects.create(board_list=todo, title="Second", position=1, created_by=user)
third = Card.objects.create(board_list=todo, title="Third", position=2, created_by=user)
client = Client()
client.force_login(user)
print(json.dumps({
  "board": board.id,
  "todo": todo.id,
  "done": done.id,
  "first": first.id,
  "second": second.id,
  "third": third.id,
  "sessionCookieName": settings.SESSION_COOKIE_NAME,
  "sessionCookieValue": client.cookies[settings.SESSION_COOKIE_NAME].value,
}))
`,
  ]),
);

const server = spawn(python, ["manage.py", "runserver", `127.0.0.1:${port}`, "--noreload"], {
  cwd: root,
  env,
  stdio: ["ignore", "pipe", "pipe"],
});

server.stdout.on("data", (chunk) => process.stdout.write(chunk));
server.stderr.on("data", (chunk) => process.stderr.write(chunk));

async function waitForServer() {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/health/`);
      if (response.ok) return;
    } catch {
      // Server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("Timed out waiting for Django test server");
}

async function cardOrder(page, listId) {
  return page
    .locator(`[data-dropzone][data-list-id="${listId}"] [data-card-id]`)
    .evaluateAll((cards) => cards.map((card) => card.textContent.trim().split(/\s+/)[0]));
}

async function pointerDrag(page, cardId, target) {
  await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes(`/cards/${cardId}/move/`) && response.request().method() === "POST",
    ),
    page.locator(`[data-card-id="${cardId}"]`).dragTo(target),
  ]);
}

async function assertNoHorizontalOverflow(page, width, height) {
  await page.setViewportSize({ width, height });
  await page.goto(`${baseUrl}/boards/${fixture.board}/`);
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  if (overflow.scrollWidth > overflow.innerWidth) {
    throw new Error(`Horizontal overflow at ${width}x${height}: ${JSON.stringify(overflow)}`);
  }
}

async function main() {
  await waitForServer();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.context().addCookies([
    {
      name: fixture.sessionCookieName,
      value: fixture.sessionCookieValue,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
  await page.goto(`${baseUrl}/boards/${fixture.board}/`);

  await pointerDrag(page, fixture.third, page.locator(`[data-card-id="${fixture.first}"]`));

  let todoOrder = await cardOrder(page, fixture.todo);
  if (todoOrder[0] !== "Third") throw new Error(`Pointer drag did not reorder Third in Todo: ${todoOrder}`);

  await page.reload();
  todoOrder = await cardOrder(page, fixture.todo);
  if (todoOrder[0] !== "Third") throw new Error(`Pointer reorder did not persist after reload: ${todoOrder}`);

  await pointerDrag(page, fixture.second, page.locator(`[data-dropzone][data-list-id="${fixture.done}"]`));

  let doneOrder = await cardOrder(page, fixture.done);
  if (doneOrder[0] !== "Second") throw new Error(`Pointer drag did not move Second to Done: ${doneOrder}`);

  await page.reload();
  doneOrder = await cardOrder(page, fixture.done);
  if (doneOrder[0] !== "Second") throw new Error(`Pointer drag did not persist after reload: ${doneOrder}`);

  await page.locator(`[data-card-id="${fixture.third}"]`).focus();
  await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes(`/cards/${fixture.third}/move/`) && response.request().method() === "POST",
    ),
    page.keyboard.press("Alt+ArrowDown"),
  ]);

  todoOrder = await cardOrder(page, fixture.todo);
  if (todoOrder[1] !== "Third") throw new Error(`Keyboard reorder did not move Third downward: ${todoOrder}`);

  await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes(`/cards/${fixture.third}/move/`) && response.request().method() === "POST",
    ),
    page.keyboard.press("Alt+ArrowRight"),
  ]);

  await page.reload();
  doneOrder = await cardOrder(page, fixture.done);
  if (!doneOrder.includes("Third")) throw new Error(`Keyboard move did not persist in Done: ${doneOrder}`);

  await assertNoHorizontalOverflow(page, 1280, 900);
  await assertNoHorizontalOverflow(page, 390, 844);

  await browser.close();
}

main()
  .finally(() => {
    server.kill();
  })
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
