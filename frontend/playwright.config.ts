import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const repoRoot = path.resolve(__dirname, "..");
const venvPython = path.join(repoRoot, ".venv", "Scripts", "python.exe");
const posixVenvPython = path.join(repoRoot, ".venv", "bin", "python");
const python = existsSync(venvPython)
  ? venvPython
  : existsSync(posixVenvPython)
    ? posixVenvPython
    : "python";

const port = Number(process.env.KIFACH_E2E_PORT ?? 8123);

/**
 * The end-to-end suite drives the delivered app: FastAPI serving the built
 * frontend on one port, with the offline mock provider and its own data
 * directory so a test run never touches a demo's saved skills.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    video: "off",
    viewport: { width: 1280, height: 720 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `"${python}" "${path.join(repoRoot, "run.py")}" --port ${port}`,
    cwd: repoRoot,
    port,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      KIFACH_PROVIDER: "mock",
      KIFACH_DATA_DIR: path.join(repoRoot, "data", "e2e"),
    },
  },
});
