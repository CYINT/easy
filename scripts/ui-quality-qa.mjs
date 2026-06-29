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
from boards.models import Board, BoardList, Card, Checklist, ChecklistItem, Comment

User = get_user_model()
user = User.objects.create_user(username="qa", email="qa@example.com", password="password-12345")
board = Board.objects.create(name="Quality Board", description="Design QA", owner=user)
todo = BoardList.objects.create(board=board, title="Todo", position=0)
done = BoardList.objects.create(board=board, title="Done", position=1)
card = Card.objects.create(board_list=todo, title="Contrast audit", description="Check visible hierarchy and movement", position=0, created_by=user)
Comment.objects.create(card=card, author=user, body="Controls should stay compact and visually consistent.")
checklist = Checklist.objects.create(card=card, title="Polish checklist", position=0)
ChecklistItem.objects.create(checklist=checklist, text="Normalize button sizes", is_done=True, position=0)
ChecklistItem.objects.create(checklist=checklist, text="Verify restrained danger buttons", position=1)
client = Client()
client.force_login(user)
print(json.dumps({
  "board": board.id,
  "card": card.id,
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
    const elements = Array.from(document.querySelectorAll(".panel, .list-column, .card, button, input, textarea, select, summary, .app-nav a, .user-chip"));
    const motionElements = Array.from(document.querySelectorAll(".card, button, .disclosure-panel summary, .app-nav a"));
    const visibleButtons = Array.from(document.querySelectorAll("button"))
      .map((element) => {
        const box = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return {
          text: element.textContent.trim(),
          className: element.className,
          width: box.width,
          height: box.height,
          background: style.backgroundColor,
          color: style.color,
          borderColor: style.borderTopColor,
          paddingLeft: px(style.paddingLeft),
          paddingRight: px(style.paddingRight),
          paddingTop: px(style.paddingTop),
          paddingBottom: px(style.paddingBottom),
        };
      })
      .filter((button) => button.width > 0 && button.height > 0);
    const normalButtons = visibleButtons.filter((button) => !button.className.includes("compact-button") && !button.className.includes("icon-button"));
    const card = document.querySelector(".card");
    const cardStyle = card ? getComputedStyle(card) : null;
    const sidebar = document.querySelector(".app-sidebar");
    const appLayout = document.querySelector(".app-layout");
    const boardMenu = document.querySelector('[data-qa-disclosure="board-menu"]');
    return {
      overflow: document.documentElement.scrollWidth > window.innerWidth,
      bodyBackgroundImage: rootStyle.backgroundImage,
      typography: {
        fontSize: px(rootStyle.fontSize),
        lineHeight: px(rootStyle.lineHeight),
        fontFamily: rootStyle.fontFamily,
      },
      shell: {
        hasLayout: Boolean(appLayout),
        sidebarWidth: sidebar?.getBoundingClientRect().width || 0,
        sidebarHeight: sidebar?.getBoundingClientRect().height || 0,
        columns: appLayout ? getComputedStyle(appLayout).gridTemplateColumns : "",
        navTargets: Array.from(document.querySelectorAll(".app-nav a")).map((item) => {
          const box = item.getBoundingClientRect();
          return { text: item.textContent.trim(), width: box.width, height: box.height };
        }),
      },
      cardContrast: cardStyle ? { color: cardStyle.color, background: cardStyle.backgroundColor } : null,
      cardPadding: cardStyle ? px(cardStyle.paddingTop) : null,
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
      buttonSystem: {
        oversized: visibleButtons.filter((button) => button.height > 48),
        excessivePadding: visibleButtons.filter((button) => button.paddingLeft > 18 || button.paddingRight > 18 || button.paddingTop > 12 || button.paddingBottom > 12),
        unclassifiedAccent: visibleButtons.filter((button) => button.background === "rgb(31, 95, 139)" && !button.className.includes("primary-button")),
        filledDanger: visibleButtons.filter((button) => button.background === "rgb(180, 35, 24)"),
        normalHeightSpread: normalButtons.length
          ? Math.max(...normalButtons.map((button) => button.height)) - Math.min(...normalButtons.map((button) => button.height))
          : 0,
      },
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
        .filter((element) => element.matches("button, input, textarea, select, summary, .app-nav a"))
        .map((element) => ({ tag: element.tagName, type: element.getAttribute("type") || "", name: element.getAttribute("name") || "", className: element.className, width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height }))
        .filter((box) => box.width > 0 && box.height > 0)
        .filter((box) => box.width < 32 || box.height < 32),
      undersizedPrimaryControls: Array.from(document.querySelectorAll('button:not(.compact-button):not(.icon-button), input:not([type="checkbox"]):not([type="radio"]), textarea, select, summary, .app-nav a'))
        .map((element) => ({
          tag: element.tagName,
          className: element.className,
          width: element.getBoundingClientRect().width,
          height: element.getBoundingClientRect().height,
        }))
        .filter((box) => box.width > 0 && box.height > 0)
        .filter((box) => box.height < 38),
      undersizedCompactControls: Array.from(document.querySelectorAll("button.compact-button, button.icon-button, input[type='checkbox'], input[type='radio']"))
        .map((element) => ({ tag: element.tagName, className: element.className, width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height }))
        .filter((box) => box.width > 0 && box.height > 0)
        .filter((box) => box.height < 34),
      icons: document.querySelectorAll(".icon").length,
      boardMenu: boardMenu
        ? {
            width: boardMenu.getBoundingClientRect().width,
            height: boardMenu.getBoundingClientRect().height,
            open: boardMenu.hasAttribute("open"),
            panelVisible: Boolean(boardMenu.querySelector(".board-menu-panel")?.getBoundingClientRect().height),
            menuSections: boardMenu.querySelectorAll(".menu-section").length,
          }
        : null,
      listColumns: Array.from(document.querySelectorAll(".list-column")).map((column) => {
        const box = column.getBoundingClientRect();
        return { width: box.width, height: box.height };
      }),
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
  if (metrics.undersizedPrimaryControls.length) throw new Error(`Primary controls below 38px height: ${JSON.stringify(metrics.undersizedPrimaryControls)}`);
  if (metrics.undersizedCompactControls.length) throw new Error(`Compact controls below 34px height: ${JSON.stringify(metrics.undersizedCompactControls)}`);
  if (metrics.bodyBackgroundImage !== "none") throw new Error(`App background should be plain, got ${metrics.bodyBackgroundImage}`);
  if (metrics.typography.fontSize < 15 || metrics.typography.fontSize > 17) throw new Error(`Body font size outside readable operational range: ${JSON.stringify(metrics.typography)}`);
  const lineHeightRatio = metrics.typography.lineHeight / metrics.typography.fontSize;
  if (lineHeightRatio < 1.35 || lineHeightRatio > 1.65) throw new Error(`Body line-height outside readable operational range: ${JSON.stringify(metrics.typography)}`);
  if (!metrics.shell.hasLayout) throw new Error("Authenticated pages should render the application shell");
  if (metrics.icons < 6) throw new Error(`Expected iconized shell and action controls, got ${metrics.icons}`);
  if (viewport.width >= 900 && metrics.shell.sidebarWidth < 180) throw new Error(`Desktop sidebar is too narrow: ${JSON.stringify(metrics.shell)}`);
  if (viewport.width < 900 && metrics.shell.sidebarHeight > 90) throw new Error(`Mobile navigation rail is too tall: ${JSON.stringify(metrics.shell)}`);
  if (metrics.shell.navTargets.length < 3) throw new Error(`Expected primary shell navigation targets: ${JSON.stringify(metrics.shell.navTargets)}`);
  if (metrics.nonZeroLetterSpacing.length) throw new Error(`Operational UI uses non-zero letter spacing: ${JSON.stringify(metrics.nonZeroLetterSpacing)}`);
  if (metrics.excessiveMotion.length) throw new Error(`Motion exceeds 250ms or uses delay: ${JSON.stringify(metrics.excessiveMotion)}`);
  if (metrics.animatedElements < 1) throw new Error("Expected bounded transitions on cards, controls, or disclosure triggers");
  if (metrics.buttonSystem.oversized.length) throw new Error(`Buttons are taller than 48px: ${JSON.stringify(metrics.buttonSystem.oversized)}`);
  if (metrics.buttonSystem.excessivePadding.length) throw new Error(`Buttons use excessive padding: ${JSON.stringify(metrics.buttonSystem.excessivePadding)}`);
  if (metrics.buttonSystem.unclassifiedAccent.length) throw new Error(`Accent buttons must use explicit primary-button intent: ${JSON.stringify(metrics.buttonSystem.unclassifiedAccent)}`);
  if (metrics.buttonSystem.filledDanger.length) throw new Error(`Danger buttons should be restrained, not filled red: ${JSON.stringify(metrics.buttonSystem.filledDanger)}`);
  if (metrics.buttonSystem.normalHeightSpread > 4) throw new Error(`Normal button heights are inconsistent: ${JSON.stringify(metrics.buttonSystem)}`);
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
  const undersizedColumns = metrics.listColumns.filter((column) => column.width < 280 || column.width > 360);
  if (undersizedColumns.length) throw new Error(`Board list column width outside expected range: ${JSON.stringify(metrics.listColumns)}`);
  if (!metrics.boardMenu || metrics.boardMenu.menuSections < 3) throw new Error(`Board menu should group list, members, and settings actions: ${JSON.stringify(metrics.boardMenu)}`);
  if (metrics.boardMenu.panelVisible) throw new Error(`Board menu panel should be closed by default: ${JSON.stringify(metrics.boardMenu)}`);
  if (metrics.cardPadding < 10 || metrics.cardPadding > 14) throw new Error(`Card padding outside dense readable range: ${metrics.cardPadding}`);
  if (!metrics.cardContrast || contrastRatio(metrics.cardContrast.color, metrics.cardContrast.background) < 4.5) {
    throw new Error(`Card text contrast below WCAG AA: ${JSON.stringify(metrics.cardContrast)}`);
  }

  await page.locator(".card").first().focus();
  const focusOutline = await page.locator(".card").first().evaluate((element) => getComputedStyle(element).outlineStyle);
  if (focusOutline === "none") throw new Error("Focused card has no visible outline");

  await page.locator('[data-qa-disclosure="board-menu"] > summary').click();
  await page.waitForSelector('[data-qa-disclosure="board-menu"][open] .board-menu-panel');
  await page.waitForSelector('[data-qa-disclosure="board-menu"][open] form[action$="/lists/"]');
  await page.locator('[data-qa-disclosure="board-members"] > summary').click();
  await page.waitForSelector('[data-qa-disclosure="board-members"][open] form[action$="/members/"]');
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

async function assertCardDetailQuality(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto(`${baseUrl}/cards/${fixture.card}/`);
  await page.waitForSelector('input[value="Contrast audit"]');

  const metrics = await collectQualityMetrics(page);
  assertSharedQuality(metrics, viewport);

  const cardPageMetrics = await page.evaluate(() => ({
    sidePanelWidth: document.querySelector(".card-side")?.getBoundingClientRect().width || 0,
    actionButtons: Array.from(document.querySelectorAll(".card-page button")).map((button) => {
      const box = button.getBoundingClientRect();
      return { text: button.textContent.trim(), className: button.className, width: box.width, height: box.height };
    }).filter((button) => button.width > 0 && button.height > 0),
    dangerButtons: Array.from(document.querySelectorAll(".card-page .danger-button")).length,
    primaryButtons: Array.from(document.querySelectorAll(".card-page .primary-button")).length,
    iconButtons: Array.from(document.querySelectorAll(".card-page .icon-button")).length,
  }));
  if (viewport.width >= 900 && cardPageMetrics.sidePanelWidth < 280) throw new Error(`Card side panel is too cramped: ${JSON.stringify(cardPageMetrics)}`);
  if (cardPageMetrics.primaryButtons < 4) throw new Error(`Card detail should mark create/save actions as primary: ${JSON.stringify(cardPageMetrics)}`);
  if (cardPageMetrics.dangerButtons < 3) throw new Error(`Card detail should use restrained danger buttons for delete actions: ${JSON.stringify(cardPageMetrics)}`);
  if (cardPageMetrics.iconButtons < 1) throw new Error(`Checklist toggles should use icon-button controls: ${JSON.stringify(cardPageMetrics)}`);
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
    await assertCardDetailQuality(page, { width: 1280, height: 900 });
    await assertCardDetailQuality(page, { width: 390, height: 844 });
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
