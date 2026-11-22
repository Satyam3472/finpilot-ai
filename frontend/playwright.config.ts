import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

const root = resolve(process.cwd(), "..");
const dataDir = mkdtempSync(join(tmpdir(), "finpilot-e2e-"));
const password = process.env.FINPILOT_E2E_PASSWORD ??= randomBytes(20).toString("hex");
const passwordFile = join(dataDir, "test_password_hash");
const signingFile = join(dataDir, "test_signing_key");
writeFileSync(passwordFile, execFileSync(join(root, ".venv/bin/python"), [
  "-c", "from argon2 import PasswordHasher; import sys; print(PasswordHasher().hash(sys.stdin.read()))",
], { input: password }), { mode: 0o600 });
writeFileSync(signingFile, randomBytes(32).toString("hex"), { mode: 0o600 });
process.on("exit", () => rmSync(dataDir, { recursive: true, force: true }));

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  projects: [{
    name: "chromium",
    use: { ...devices["Desktop Chrome"], channel: process.env.FINPILOT_BROWSER || undefined },
  }],
  webServer: [
    {
      cwd: root,
      command: ".venv/bin/python -m uvicorn backend.main:app --port 8000",
      url: "http://127.0.0.1:8000/api/health",
      env: { FINPILOT_DATA_DIR: dataDir, FINPILOT_LOCAL_USER: "finpilot-browser-tests", FINPILOT_PASSWORD_HASH_FILE: passwordFile, FINPILOT_SESSION_SECRET_FILE: signingFile },
      reuseExistingServer: false,
    },
    {
      command: "npm run start",
      url: "http://127.0.0.1:3000/dashboard",
      env: { NEXT_TELEMETRY_DISABLED: "1", FINPILOT_BACKEND_URL: "http://127.0.0.1:8000" },
      reuseExistingServer: false,
    },
  ],
});
