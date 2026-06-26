import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const baseUrl = process.env.EASY_LIVE_URL || "http://127.0.0.1:18082";
const email = process.env.EASY_AUTH_QA_EMAIL || "livepasskeyqa@example.com";
const username = process.env.EASY_AUTH_QA_USERNAME || "livepasskeyqa";
const password = process.env.EASY_AUTH_QA_PASSWORD || "password-12345";
const envFile = process.env.EASY_COMPOSE_ENV || ".env.local";

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
  await page.waitForURL(/\/boards\//);
  const body = await page.locator("body").innerText();
  if (!body.includes("Successfully signed in")) {
    throw new Error("Email/password login did not reach the board dashboard.");
  }
}

async function enrollPasswordlessPasskey(page) {
  await page.goto(`${baseUrl}/accounts/2fa/webauthn/add/`);
  await page.locator('input[name="name"]').fill("QA Passwordless Passkey");
  await page.locator('input[name="passwordless"]').check();
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.waitForURL(/\/accounts\/2fa\/recovery-codes\//);
  const body = await page.locator("body").innerText();
  if (!body.includes("Security key added")) {
    throw new Error("Passkey enrollment did not complete.");
  }
}

async function logout(page) {
  await page.goto(`${baseUrl}/accounts/logout/`);
  await page.getByRole("button", { name: "Sign Out", exact: true }).click();
  await page.waitForURL(/\/accounts\/login\//);
}

async function passkeyLogin(page) {
  await page.goto(`${baseUrl}/accounts/login/`);
  await page.getByRole("button", { name: "Sign in with a passkey" }).click();
  await page.waitForURL(/\/boards\//);
  const body = await page.locator("body").innerText();
  if (!body.includes(`Successfully signed in as ${username}`)) {
    throw new Error("Passwordless passkey login did not reach the board dashboard.");
  }
}

const browser = await chromium.launch();
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });

  await passwordLogin(page);
  await enrollPasswordlessPasskey(page);
  await logout(page);
  await passkeyLogin(page);
} finally {
  await browser.close();
}
