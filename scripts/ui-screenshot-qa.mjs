import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PNG } from "pngjs";
import { chromium } from "playwright";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const qaDir = path.join(root, ".easy-qa");
const screenshotDir = path.join(qaDir, "screenshots");
const dbPath = path.join(qaDir, "ui-screenshot.sqlite3");
const port = Number(process.env.EASY_SCREENSHOT_QA_PORT || 28767);
const baseUrl = `http://127.0.0.1:${port}`;
const python = process.env.PYTHON || path.join(root, ".venv", "Scripts", "python.exe");

fs.mkdirSync(screenshotDir, { recursive: true });
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

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function analyzePng(filePath) {
  const png = PNG.sync.read(fs.readFileSync(filePath));
  const colors = new Set();
  let nonWhite = 0;
  const step = Math.max(4, Math.floor((png.width * png.height) / 30_000));
  for (let pixel = 0; pixel < png.width * png.height; pixel += step) {
    const offset = pixel * 4;
    const r = png.data[offset];
    const g = png.data[offset + 1];
    const b = png.data[offset + 2];
    colors.add(`${r >> 4},${g >> 4},${b >> 4}`);
    if (r < 248 || g < 248 || b < 248) nonWhite += 1;
  }
  return { width: png.width, height: png.height, colors: colors.size, nonWhite };
}

async function capture(page, name) {
  const filePath = path.join(screenshotDir, `${name}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  const pixels = analyzePng(filePath);
  assert(pixels.colors >= 16, `${name} screenshot has too little visual variation: ${JSON.stringify(pixels)}`);
  assert(pixels.nonWhite >= 300, `${name} screenshot appears blank: ${JSON.stringify(pixels)}`);
  return filePath;
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
board = Board.objects.create(name="Design Review Board", description="Menu, icon, and spacing QA", owner=user)
todo = BoardList.objects.create(board=board, title="Todo", position=0)
doing = BoardList.objects.create(board=board, title="Doing", position=1)
done = BoardList.objects.create(board=board, title="Done", position=2)
Card.objects.create(board_list=todo, title="Audit spacing", description="Check visual rhythm, icon alignment, and menu placement", position=0, created_by=user)
Card.objects.create(board_list=todo, title="Review controls", description="Buttons should be easy to hit without bloating the board", position=1, created_by=user)
Card.objects.create(board_list=doing, title="Validate screenshots", description="Desktop and mobile captures should be nonblank and balanced", position=0, created_by=user)
client = Client()
client.force_login(user)
print(json.dumps({
  "board": board.id,
  "todo": todo.id,
  "doing": doing.id,
  "done": done.id,
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

async function assertNoOverflow(page, label) {
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(overflow.scrollWidth <= overflow.clientWidth, `${label} has horizontal overflow: ${JSON.stringify(overflow)}`);
}

async function assertIconRendering(page, label) {
  const icons = await page.locator(".icon").evaluateAll((nodes) =>
    nodes.map((node) => {
      const box = node.getBoundingClientRect();
      return { width: box.width, height: box.height };
    }).filter((box) => box.width > 0 && box.height > 0),
  );
  assert(icons.length >= 6, `${label} expected iconized controls, found ${icons.length}`);
  const badIcons = icons.filter((icon) => icon.width < 12 || icon.height < 12 || icon.width > 24 || icon.height > 24);
  assert(!badIcons.length, `${label} has poorly sized icons: ${JSON.stringify(badIcons)}`);
}

async function assertBoardMenu(page, viewportName) {
  await page.locator('[data-qa-disclosure="board-menu"] > summary').click();
  await page.waitForSelector('[data-qa-disclosure="board-menu"][open] .board-menu-panel');
  const metrics = await page.evaluate(() => {
    const panel = document.querySelector(".board-menu-panel").getBoundingClientRect();
    const header = document.querySelector(".site-header").getBoundingClientRect();
    const board = document.querySelector(".board").getBoundingClientRect();
    return {
      panel: { left: panel.left, top: panel.top, right: panel.right, bottom: panel.bottom, width: panel.width, height: panel.height },
      headerBottom: header.bottom,
      boardTop: board.top,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    };
  });
  assert(metrics.panel.left >= 0, `${viewportName} board menu spills left: ${JSON.stringify(metrics)}`);
  assert(metrics.panel.right <= metrics.viewportWidth + 1, `${viewportName} board menu spills right: ${JSON.stringify(metrics)}`);
  assert(metrics.panel.top >= metrics.headerBottom - 1, `${viewportName} board menu overlaps header: ${JSON.stringify(metrics)}`);
  assert(metrics.panel.width >= Math.min(340, metrics.viewportWidth - 24), `${viewportName} board menu is too narrow: ${JSON.stringify(metrics)}`);
  assert(metrics.panel.height >= 220, `${viewportName} board menu is too short to expose actions: ${JSON.stringify(metrics)}`);
  await capture(page, `board-menu-${viewportName}`);
}

async function assertListMenu(page, viewportName) {
  await page.locator('[data-qa-disclosure="list-actions"] > summary').first().click();
  await page.waitForSelector('[data-qa-disclosure="list-actions"][open] .list-menu-panel');
  const metrics = await page.evaluate(() => {
    const panel = document.querySelector(".list-menu-panel").getBoundingClientRect();
    return {
      panel: { left: panel.left, right: panel.right, width: panel.width, height: panel.height },
      viewportWidth: window.innerWidth,
    };
  });
  assert(metrics.panel.left >= 0, `${viewportName} list menu spills left: ${JSON.stringify(metrics)}`);
  assert(metrics.panel.right <= metrics.viewportWidth + 1, `${viewportName} list menu spills right: ${JSON.stringify(metrics)}`);
}

async function main() {
  await waitForServer();
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext();
    await context.addCookies([
      {
        name: fixture.sessionCookieName,
        value: fixture.sessionCookieValue,
        domain: "127.0.0.1",
        path: "/",
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);
    const page = await context.newPage();

    for (const [viewportName, viewport] of Object.entries({
      desktop: { width: 1440, height: 920 },
      mobile: { width: 390, height: 844 },
    })) {
      await page.setViewportSize(viewport);
      await page.goto(`${baseUrl}/boards/`);
      await page.waitForSelector("text=Your boards");
      await assertNoOverflow(page, `${viewportName} dashboard`);
      await assertIconRendering(page, `${viewportName} dashboard`);
      await capture(page, `dashboard-${viewportName}`);

      await page.goto(`${baseUrl}/boards/${fixture.board}/`);
      await page.waitForSelector("text=Design Review Board");
      await assertNoOverflow(page, `${viewportName} board`);
      await assertIconRendering(page, `${viewportName} board`);
      await capture(page, `board-${viewportName}`);
      await assertBoardMenu(page, viewportName);
      await assertListMenu(page, viewportName);
    }

    console.log(`screenshots=${screenshotDir}`);
  } finally {
    await browser.close();
  }
}

main()
  .finally(() => {
    server.kill();
  })
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
