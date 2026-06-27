import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const args = process.argv.slice(2);
const flags = new Set(args.filter((arg) => arg.startsWith("--")));
const versionArg = args.find((arg) => !arg.startsWith("--"));
const packageJson = JSON.parse(readFileSync("package.json", "utf8"));
const version = versionArg || `v${packageJson.version}`;
const createTag = process.env.EASY_RELEASE_CREATE_TAG === "true" || flags.has("--create");
const pushTag = process.env.EASY_RELEASE_PUSH === "true" || flags.has("--push");
const dryRun = flags.has("--dry-run") || !createTag;

function run(command, commandArgs, options = {}) {
  const result = spawnSync(command, commandArgs, {
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

function fail(message, evidence = {}) {
  console.error(JSON.stringify({ ok: false, message, evidence }, null, 2));
  process.exit(1);
}

if (!/^v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(version)) {
  fail("release version must look like v0.1.0", { version });
}

if (pushTag && dryRun) {
  fail("cannot push during dry run; set EASY_RELEASE_CREATE_TAG=true or pass --create");
}

const existingTag = run("git", ["tag", "--list", version]);
if (existingTag.status !== 0) {
  fail("failed to inspect existing tags", { version, stderr: existingTag.stderr, error: existingTag.error });
}
if (existingTag.stdout === version) {
  fail("release tag already exists locally", { version });
}

const remoteTag = run("git", ["ls-remote", "--tags", "origin", `refs/tags/${version}`]);
if (remoteTag.status !== 0) {
  fail("failed to inspect remote tags", { version, stderr: remoteTag.stderr, error: remoteTag.error });
}
if (remoteTag.stdout) {
  fail("release tag already exists on origin", { version, remote: remoteTag.stdout });
}

const gates = run(process.execPath, ["scripts/release-gates.mjs"], { env: process.env });
let gateEvidence = gates.stdout || gates.stderr || gates.error;
try {
  gateEvidence = JSON.parse(gateEvidence);
} catch {
  // Preserve raw output when parsing fails.
}

if (gates.status !== 0) {
  fail("release gates failed; refusing to create release tag", { version, gateEvidence });
}

if (dryRun) {
  console.log(
    JSON.stringify(
      {
        ok: true,
        dryRun: true,
        version,
        message: "release gates passed; set EASY_RELEASE_CREATE_TAG=true to create the tag",
        gateEvidence,
      },
      null,
      2,
    ),
  );
  process.exit(0);
}

const message = process.env.EASY_RELEASE_TAG_MESSAGE || `Easy ${version} release`;
const tag = run("git", ["tag", "-a", version, "-m", message]);
if (tag.status !== 0) {
  fail("failed to create annotated release tag", { version, stderr: tag.stderr, error: tag.error });
}

let pushEvidence = null;
if (pushTag) {
  const push = run("git", ["push", "origin", version]);
  pushEvidence = { status: push.status, stdout: push.stdout, stderr: push.stderr, error: push.error };
  if (push.status !== 0) {
    fail("release tag was created locally but failed to push", { version, pushEvidence });
  }
}

console.log(
  JSON.stringify(
    {
      ok: true,
      dryRun: false,
      version,
      pushed: pushTag,
      message,
      pushEvidence,
      gateEvidence,
    },
    null,
    2,
  ),
);
