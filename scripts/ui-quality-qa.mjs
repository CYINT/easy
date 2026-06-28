import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const qaDir = path.join(root, ".easy-qa");
const dbPath = path.join(qaDir, "ui-quality.sqlite3");
const port = Number(process.env.EASY_UI_QA_PORT || 28766);
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

function rgbToLuminance(rgb) {
  const channels = rgb.match(/\d+(\.\d+)?/g)?.slice(0, 3).map(Number) ?? [];
  if (channels.length !== 3) return 0;
  const normalized = channels.map((value) => {
    const channel = value / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * normalized[0] + 0.7152 * normalized[1] + 0.0722 * normalized[2];
}

function contrastRatio(foreground, background) {
  const light = Math.max(rgbToLuminance(foreground), rgbToLuminance(background));
  const dark = Math.min(rgbToLuminance(foreground), rgbToLuminance(background));
  return (light + 0.05) / (dark + 0.05);
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
board = Board.objects.create(name="Quality Board", description="Design QA", owner=user)
todo = BoardList.objects.create(board=board, title="Todo", position=0)
done = BoardList.objects.create(board=board, title="Done", position=1)
Card.objects.create(board_list=todo, title="Contrast audit", description="Check visible hierarchy and movement", position=0, created_by=user)
client = Client()
client.force_login(user)
print(json.dumps({
  "board": board.id,
  "todo": todo.id,
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

async function collectQualityMetrics(page) {
  return page.evaluate((doneListId) => {
    const px = (value) => Number.parseFloat(value) || 0;
    const rootStyle = getComputedStyle(document.body);
    const elements = Array.from(document.querySelectorAll(".panel, .list-column, .card, button, input, textarea, select"));
    const card = document.querySelector(".card");
    const cardStyle = card ? getComputedStyle(card) : null;
    return {
      overflow: document.documentElement.scrollWidth > window.innerWidth,
      bodyBackgroundImage: rootStyle.backgroundImage,
      cardContrast: cardStyle ? { color: cardStyle.color, background: cardStyle.backgroundColor } : null,
      maxRadius: Math.max(...elements.map((element) => px(getComputedStyle(element).borderTopLeftRadius))),
      smallTargets: elements
        .filter((element) => element.matches("button, input, textarea, select"))
        .map((element) => ({ tag: element.tagName, width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height }))
        .filter((box) => box.width > 0 && box.height > 0)
        .filter((box) => box.width < 32 || box.height < 32),
      emptyDropzone: (() => {
        const zone = document.querySelector(`[data-dropzone][data-list-id="${doneListId}"]`);
        if (!zone) return null;
        const box = zone.getBoundingClientRect();
        return { width: box.width, height: box.height };
      })(),
    };
  }, fixture.done);
}

async function assertQuality(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto(`${baseUrl}/boards/${fixture.board}/`);
  await page.waitForSelector("text=Quality Board");

  const metrics = await collectQualityMetrics(page);
  if (metrics.overflow) throw new Error(`Horizontal overflow at ${viewport.width}x${viewport.height}`);
  if (metrics.maxRadius > 8) throw new Error(`Operational UI radius exceeds 8px: ${metrics.maxRadius}`);
  if (metrics.smallTargets.length) throw new Error(`Controls below 32px target size: ${JSON.stringify(metrics.smallTargets)}`);
  if (!metrics.emptyDropzone || metrics.emptyDropzone.height < 80) {
    throw new Error(`Empty drop zone is too small: ${JSON.stringify(metrics.emptyDropzone)}`);
  }
  if (metrics.bodyBackgroundImage !== "none") throw new Error(`App background should be plain, got ${metrics.bodyBackgroundImage}`);
  if (!metrics.cardContrast || contrastRatio(metrics.cardContrast.color, metrics.cardContrast.background) < 4.5) {
    throw new Error(`Card text contrast below WCAG AA: ${JSON.stringify(metrics.cardContrast)}`);
  }

  await page.locator(".card").first().focus();
  const focusOutline = await page.locator(".card").first().evaluate((element) => getComputedStyle(element).outlineStyle);
  if (focusOutline === "none") throw new Error("Focused card has no visible outline");
}

async function main() {
  await waitForServer();
  const browser = await chromium.launch();
  try {
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

    await assertQuality(page, { width: 1280, height: 900 });
    await assertQuality(page, { width: 390, height: 844 });
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
