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
    const cssTimeToMs = (value) => {
      if (!value) return 0;
      const trimmed = value.trim();
      if (trimmed.endsWith("ms")) return Number.parseFloat(trimmed);
      if (trimmed.endsWith("s")) return Number.parseFloat(trimmed) * 1000;
      return Number.parseFloat(trimmed) || 0;
    };
    const cssTimes = (value) => value.split(",").map((part) => part.trim()).filter(Boolean);
    const rootStyle = getComputedStyle(document.body);
    const elements = Array.from(document.querySelectorAll(".panel, .list-column, .card, button, input, textarea, select, summary"));
    const motionElements = Array.from(document.querySelectorAll(".card, button, .disclosure-panel summary"));
    const card = document.querySelector(".card");
    const cardStyle = card ? getComputedStyle(card) : null;
    return {
      overflow: document.documentElement.scrollWidth > window.innerWidth,
      bodyBackgroundImage: rootStyle.backgroundImage,
      cardContrast: cardStyle ? { color: cardStyle.color, background: cardStyle.backgroundColor } : null,
      maxRadius: Math.max(...elements.map((element) => px(getComputedStyle(element).borderTopLeftRadius))),
      nonZeroLetterSpacing: elements
        .map((element) => ({ tag: element.tagName, className: element.className, value: getComputedStyle(element).letterSpacing }))
        .filter((item) => item.value !== "normal" && px(item.value) !== 0),
      excessiveMotion: motionElements
        .flatMap((element) => {
          const style = getComputedStyle(element);
          const delays = cssTimes(style.transitionDelay);
          return cssTimes(style.transitionDuration).map((duration, index) => ({
            tag: element.tagName,
            className: element.className,
            duration,
            delay: delays[index] || "0s",
          }));
        })
        .filter((item) => cssTimeToMs(item.duration) > 250 || cssTimeToMs(item.delay) > 0),
      animatedElements: motionElements
        .map((element) => getComputedStyle(element).transitionDuration)
        .filter((duration) => cssTimes(duration).some((part) => cssTimeToMs(part) > 0))
        .length,
      hiddenDisclosureForms: Array.from(document.querySelectorAll("[data-qa-disclosure]:not([open])")).map((details) => {
        const content = details.querySelector("form, .member-grid");
        const box = content?.getBoundingClientRect();
        return {
          name: details.getAttribute("data-qa-disclosure"),
          visibleWidth: box?.width || 0,
          visibleHeight: box?.height || 0,
        };
      }),
      smallTargets: elements
        .filter((element) => element.matches("button, input, textarea, select, summary"))
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

function assertSharedQuality(metrics, viewport) {
  if (metrics.overflow) throw new Error(`Horizontal overflow at ${viewport.width}x${viewport.height}`);
  if (metrics.maxRadius > 8) throw new Error(`Operational UI radius exceeds 8px: ${metrics.maxRadius}`);
  if (metrics.smallTargets.length) throw new Error(`Controls below 32px target size: ${JSON.stringify(metrics.smallTargets)}`);
  if (metrics.bodyBackgroundImage !== "none") throw new Error(`App background should be plain, got ${metrics.bodyBackgroundImage}`);
  if (metrics.nonZeroLetterSpacing.length) throw new Error(`Operational UI uses non-zero letter spacing: ${JSON.stringify(metrics.nonZeroLetterSpacing)}`);
  if (metrics.excessiveMotion.length) throw new Error(`Motion exceeds 250ms or uses delay: ${JSON.stringify(metrics.excessiveMotion)}`);
  if (metrics.animatedElements < 1) throw new Error("Expected bounded transitions on cards, controls, or disclosure triggers");
  const visibleClosedForms = metrics.hiddenDisclosureForms.filter((item) => item.visibleWidth > 0 || item.visibleHeight > 0);
  if (visibleClosedForms.length) throw new Error(`Closed disclosure content is visible: ${JSON.stringify(visibleClosedForms)}`);
}

async function assertBoardQuality(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto(`${baseUrl}/boards/${fixture.board}/`);
  await page.waitForSelector("text=Quality Board");

  const metrics = await collectQualityMetrics(page);
  assertSharedQuality(metrics, viewport);
  if (!metrics.emptyDropzone || metrics.emptyDropzone.height < 80) {
    throw new Error(`Empty drop zone is too small: ${JSON.stringify(metrics.emptyDropzone)}`);
  }
  if (!metrics.cardContrast || contrastRatio(metrics.cardContrast.color, metrics.cardContrast.background) < 4.5) {
    throw new Error(`Card text contrast below WCAG AA: ${JSON.stringify(metrics.cardContrast)}`);
  }

  await page.locator(".card").first().focus();
  const focusOutline = await page.locator(".card").first().evaluate((element) => getComputedStyle(element).outlineStyle);
  if (focusOutline === "none") throw new Error("Focused card has no visible outline");

  await page.locator('[data-qa-disclosure="add-list"] > summary').click();
  await page.waitForSelector('[data-qa-disclosure="add-list"][open] form');
  await page.locator('[data-qa-disclosure="add-card"] > summary').first().click();
  await page.waitForSelector('[data-qa-disclosure="add-card"][open] form');
}

async function assertDashboardQuality(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto(`${baseUrl}/boards/`);
  await page.waitForSelector("text=Your boards");

  const metrics = await collectQualityMetrics(page);
  assertSharedQuality(metrics, viewport);

  await page.locator('[data-qa-disclosure="create-board"] > summary').click();
  await page.waitForSelector('[data-qa-disclosure="create-board"][open] form');
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

    await assertDashboardQuality(page, { width: 1280, height: 900 });
    await assertDashboardQuality(page, { width: 390, height: 844 });
    await assertBoardQuality(page, { width: 1280, height: 900 });
    await assertBoardQuality(page, { width: 390, height: 844 });
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
