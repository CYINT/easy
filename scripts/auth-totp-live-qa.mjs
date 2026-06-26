import crypto from "node:crypto";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const baseUrl = process.env.EASY_LIVE_URL || "https://easy.kuzuryu.ai";
const email = process.env.EASY_TOTP_QA_EMAIL || "livetotpqa@example.com";
const username = process.env.EASY_TOTP_QA_USERNAME || "livetotpqa";
const password = process.env.EASY_TOTP_QA_PASSWORD || "password-12345";
const envFile = process.env.EASY_COMPOSE_ENV || "C:\\Users\\Dan\\.cyint\\easy\\easy.env";

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: root,
    encoding: "utf8",
  });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed\n${result.stdout || ""}\n${result.stderr || ""}`);
  }
  return (result.stdout || "").trim();
}

function base32Decode(value) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const clean = value.toUpperCase().replace(/=+$/g, "").replace(/\s+/g, "");
  const bytes = [];
  let bits = 0;
  let buffer = 0;

  for (const char of clean) {
    const index = alphabet.indexOf(char);
    if (index === -1) {
      throw new Error(`Invalid base32 character in TOTP secret: ${char}`);
    }
    buffer = (buffer << 5) | index;
    bits += 5;
    if (bits >= 8) {
      bytes.push((buffer >> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Buffer.from(bytes);
}

function totp(secret, timestamp = Date.now()) {
  const key = base32Decode(secret);
  const counter = Math.floor(timestamp / 1000 / 30);
  const counterBuffer = Buffer.alloc(8);
  counterBuffer.writeBigUInt64BE(BigInt(counter));
  const digest = crypto.createHmac("sha1", key).update(counterBuffer).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const binary =
    ((digest[offset] & 0x7f) << 24) |
    ((digest[offset + 1] & 0xff) << 16) |
    ((digest[offset + 2] & 0xff) << 8) |
    (digest[offset + 3] & 0xff);
  return String(binary % 1_000_000).padStart(6, "0");
}

run("docker", [
  "compose",
  "--env-file",
  envFile,
  "exec",
  "-T",
  "easy",
  "python",
  "manage.py",
  "shell",
  "-c",
  `
from django.contrib.auth import get_user_model
from allauth.mfa.models import Authenticator

User = get_user_model()
user, _ = User.objects.update_or_create(username="${username}", defaults={"email": "${email}"})
user.set_password("${password}")
user.save()
Authenticator.objects.filter(user=user).delete()
print({"user_id": user.id, "email": user.email})
`,
]);

async function passwordLogin(page) {
  await page.goto(`${baseUrl}/accounts/login/`);
  await page.locator('input[name="login"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
}

async function assertDashboard(page, expectedText = "Successfully signed in") {
  await page.waitForURL(/\/boards\//);
  const body = await page.locator("body").innerText();
  if (!body.includes(expectedText)) {
    throw new Error("Login did not reach the board dashboard.");
  }
}

async function maybeReauthenticate(page) {
  if (!page.url().includes("/accounts/reauthenticate/")) {
    return;
  }
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: /confirm|reauthenticate|sign in/i }).click();
}

async function enrollTotp(page) {
  await page.goto(`${baseUrl}/accounts/2fa/totp/activate/`);
  await maybeReauthenticate(page);
  await page.waitForURL(/\/accounts\/2fa\/totp\/activate\//);
  const secret = await page.locator("#authenticator_secret").inputValue();
  if (!secret) {
    throw new Error("TOTP activation page did not expose an authenticator secret.");
  }
  await page.locator('input[name="code"]').fill(totp(secret));
  await page.getByRole("button", { name: "Activate", exact: true }).click();
  await page.waitForURL(/\/accounts\/2fa\/(recovery-codes|$)/);
  const body = await page.locator("body").innerText();
  if (!body.includes("Authenticator app activated") && !body.includes("Recovery Codes")) {
    throw new Error("Authenticator app activation did not complete.");
  }
  return secret;
}

async function logout(page) {
  await page.goto(`${baseUrl}/accounts/logout/`);
  await page.getByRole("button", { name: "Sign Out", exact: true }).click();
  await page.waitForURL(/\/accounts\/login\//);
}

async function totpLogin(page, secret) {
  await passwordLogin(page);
  await page.waitForURL(/\/accounts\/2fa\/authenticate\//);
  await page.locator('input[name="code"]').fill(totp(secret));
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await assertDashboard(page, `Successfully signed in as ${username}`);
}

const browser = await chromium.launch();
try {
  const context = await browser.newContext();
  const page = await context.newPage();

  await passwordLogin(page);
  await assertDashboard(page);
  const secret = await enrollTotp(page);
  await logout(page);
  await totpLogin(page, secret);
} finally {
  await browser.close();
}
