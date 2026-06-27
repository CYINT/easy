import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import os from "node:os";

const hostname = process.env.EASY_RELEASE_HOSTNAME || process.env.EASY_HOSTNAME;
const baseUrl = process.env.EASY_RELEASE_BASE_URL || (hostname ? `https://${hostname}` : "");
const privateBetaAccepted = process.env.EASY_RELEASE_PRIVATE_BETA_ACCEPTED === "true";
const googleOAuthEnabled = process.env.EASY_ENABLE_GOOGLE_OAUTH === "true";
const googleOAuthTested = process.env.EASY_RELEASE_GOOGLE_OAUTH_TESTED === "true";
const skipTlsVerify = process.env.EASY_RELEASE_SKIP_TLS_VERIFY === "true";
const releaseNotesPath = process.env.EASY_RELEASE_NOTES_PATH || "";

const failures = [];
const evidence = {};

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    shell: false,
    ...options,
  });
  return {
    status: result.status,
    stdout: (result.stdout || "").trim(),
    stderr: (result.stderr || "").trim(),
    error: result.error?.message || "",
  };
}

function commandExists(command) {
  const probe = process.platform === "win32" ? run("where.exe", [command]) : run("which", [command]);
  return probe.status === 0;
}

function curlCommand() {
  if (process.platform === "win32" && commandExists("curl.exe")) return "curl.exe";
  return "curl";
}

function checkGitCleanAndPushed() {
  const status = run("git", ["status", "--porcelain"]);
  if (status.status !== 0) {
    failures.push(`git status failed: ${status.stderr || status.error}`);
    return;
  }
  evidence.gitStatus = status.stdout || "clean";
  if (status.stdout) failures.push("working tree is not clean");

  const head = run("git", ["rev-parse", "HEAD"]);
  if (head.status !== 0) {
    failures.push(`git rev-parse HEAD failed: ${head.stderr || head.error}`);
    return;
  }

  const remote = run("git", ["ls-remote", "origin", "refs/heads/main"]);
  if (remote.status !== 0) {
    failures.push(`git ls-remote origin main failed: ${remote.stderr || remote.error}`);
    return;
  }
  const remoteSha = remote.stdout.split(/\s+/)[0] || "";
  evidence.gitHead = head.stdout;
  evidence.originMain = remoteSha;
  if (head.stdout !== remoteSha) failures.push("local HEAD does not match origin/main");
}

function checkGoogleOAuthPosture() {
  evidence.googleOAuthEnabled = googleOAuthEnabled;
  evidence.googleOAuthTested = googleOAuthTested;
  if (googleOAuthEnabled && !googleOAuthTested) {
    failures.push("Google OAuth is enabled but EASY_RELEASE_GOOGLE_OAUTH_TESTED=true was not set");
  }
}

function checkLiveEndpoint(path) {
  const curl = curlCommand();
  const args = [
    "-sS",
    "--connect-timeout",
    "10",
    "-o",
    os.devNull,
    "-w",
    "%{http_code} %{ssl_verify_result}",
  ];
  if (skipTlsVerify) args.unshift("-k");
  args.push(`${baseUrl}${path}`);

  const result = run(curl, args);
  return {
    ok: result.status === 0 && result.stdout.startsWith("200 "),
    output: result.stdout || result.stderr || result.error,
  };
}

function checkLiveSmoke() {
  if (!baseUrl) {
    failures.push("set EASY_RELEASE_HOSTNAME or EASY_RELEASE_BASE_URL before running release gates");
    return;
  }

  evidence.baseUrl = baseUrl;
  evidence.live = {
    health: checkLiveEndpoint("/health/"),
    app: checkLiveEndpoint("/app/"),
    openapi: checkLiveEndpoint("/api/v1/openapi.json"),
  };

  for (const [name, result] of Object.entries(evidence.live)) {
    if (!result.ok) failures.push(`${name} endpoint did not return HTTP 200 with valid TLS: ${result.output}`);
  }
}

function checkPublicIngress() {
  if (!hostname) {
    failures.push("set EASY_RELEASE_HOSTNAME or EASY_HOSTNAME before checking public ingress");
    return;
  }

  const probe = run(process.execPath, ["scripts/public-ingress-probe.mjs"], {
    env: { ...process.env, EASY_HOSTNAME: hostname },
  });
  evidence.publicIngressProbe = {
    status: probe.status,
    output: probe.stdout || probe.stderr || probe.error,
  };

  let parsed = null;
  try {
    const jsonStart = evidence.publicIngressProbe.output.indexOf("{");
    parsed = JSON.parse(evidence.publicIngressProbe.output.slice(jsonStart));
    evidence.publicIngressProbe.parsed = parsed;
  } catch {
    failures.push("public ingress probe did not produce parseable JSON");
    return;
  }

  const publicHttpsOk = Boolean(parsed?.wanHealth?.ok);
  evidence.publicHttpsOk = publicHttpsOk;
  evidence.privateBetaAccepted = privateBetaAccepted;

  if (!publicHttpsOk && !privateBetaAccepted) {
    failures.push(
      "public HTTPS ingress is not verified; set EASY_RELEASE_PRIVATE_BETA_ACCEPTED=true only for an explicitly accepted private-beta release",
    );
  }
}

function checkPrivateBetaReleaseNotes() {
  evidence.releaseNotesPath = releaseNotesPath || null;
  if (!privateBetaAccepted) return;

  if (!releaseNotesPath) {
    failures.push("set EASY_RELEASE_NOTES_PATH to release notes that record the accepted private-beta access boundary");
    return;
  }

  if (!existsSync(releaseNotesPath)) {
    failures.push(`release notes file does not exist: ${releaseNotesPath}`);
    return;
  }

  const notes = readFileSync(releaseNotesPath, "utf8").toLowerCase();
  const mentionsPrivateBeta = notes.includes("private beta");
  const mentionsBoundary =
    notes.includes("private network") ||
    notes.includes("private-network") ||
    notes.includes("dragonscale") ||
    notes.includes("tunnel");
  const avoidsPublicClaim =
    notes.includes("not publicly reachable") ||
    notes.includes("not publicly internet reachable") ||
    notes.includes("do not describe this release as publicly internet reachable");

  evidence.releaseNotes = {
    privateBeta: mentionsPrivateBeta,
    accessBoundary: mentionsBoundary,
    avoidsPublicClaim,
  };

  if (!mentionsPrivateBeta || !mentionsBoundary || !avoidsPublicClaim) {
    failures.push("private-beta release notes must state private beta status, access boundary, and no-public-reachability claim");
  }
}

checkGitCleanAndPushed();
checkGoogleOAuthPosture();
checkLiveSmoke();
checkPublicIngress();
checkPrivateBetaReleaseNotes();

console.log(JSON.stringify({ ok: failures.length === 0, failures, evidence }, null, 2));

if (failures.length > 0) {
  process.exit(1);
}
