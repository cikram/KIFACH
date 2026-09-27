import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * The delivery test: the whole product loop against the running app, with the
 * offline mock provider. It also captures the screenshots used in the README
 * and checks that no page logged a console error along the way.
 */

const SHOTS = path.resolve(__dirname, "..", "..", "docs", "screenshots");
const SAMPLES = path.resolve(__dirname, "..", "..", "samples");

let consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(String(error)));
});

test.afterEach(() => {
  const ignorable = (text: string) =>
    text.includes("favicon") || text.includes("ResizeObserver");
  const real = consoleErrors.filter((text) => !ignorable(text));
  expect(real, `browser console errors: ${real.join(" | ")}`).toHaveLength(0);
});

async function teachAndPublish(page: Page): Promise<string> {
  await page.goto("/#/teach");
  await page.setInputFiles(
    '[data-testid="file-input-expert"]',
    path.join(SAMPLES, "expert.webm"),
  );
  await expect(page.getByTestId("evidence-video")).toBeVisible();
  await page.getByTestId("task-hint").fill("light an LED on a breadboard");
  await page.getByTestId("start-teach").click();

  await expect(page.getByTestId("window-list").locator("li").first()).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByTestId("go-review")).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: path.join(SHOTS, "02-teach.png"), fullPage: true });

  await page.getByTestId("go-review").click();
  await expect(page).toHaveURL(/#\/review\//, { timeout: 30_000 });
  await expect(page.getByTestId("skill-status")).toHaveText("draft");
  await expect(page.getByTestId("procedure-graph")).toBeVisible();

  // An unreviewed proposal must not be publishable.
  await page.getByTestId("publish-skill").click();
  await expect(page.getByRole("alert")).toContainText(/Confirm or remove/i);
  await page.screenshot({ path: path.join(SHOTS, "03-review.png"), fullPage: true });

  await page.getByTestId("confirm-rule").click();
  await expect(page.getByTestId("rule-confirmed")).toBeVisible();
  await page.getByTestId("publish-skill").click();
  await expect(page.getByTestId("skill-status")).toHaveText("published", {
    timeout: 20_000,
  });
  await page.screenshot({ path: path.join(SHOTS, "04-published.png"), fullPage: true });

  const url = page.url();
  const skillId = url.split("/review/")[1];
  expect(skillId).toBeTruthy();
  return skillId;
}

async function runAttempt(page: Page, skillId: string, sample: string): Promise<void> {
  await page.goto(`/#/practice/${skillId}`);
  await page.setInputFiles(
    '[data-testid="file-input-attempt"]',
    path.join(SAMPLES, sample),
  );
  await expect(page).toHaveURL(/#\/attempt\//, { timeout: 90_000 });
  await expect(page.getByTestId("verdict-panel")).toBeVisible();
}

test("the whole loop: teach, review, publish, and assess five attempts", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByTestId("provider-status")).toContainText("MOCK");
  await page.screenshot({ path: path.join(SHOTS, "01-home.png"), fullPage: true });

  const skillId = await teachAndPublish(page);

  // 1. A correct attempt is verified.
  await runAttempt(page, skillId, "correct.webm");
  await expect(page.getByTestId("verdict-VERIFIED")).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, "05-verified.png"), fullPage: true });

  // Replay must reproduce the stored result exactly.
  await page.getByTestId("replay-attempt").click();
  await expect(page.getByTestId("replay-result")).toContainText("reproduced this result");

  // 2. A supported wrong order fails, and its evidence seeks the video.
  await runAttempt(page, skillId, "wrong_order.webm");
  await expect(page.getByTestId("verdict-NOT_VERIFIED")).toBeVisible();
  await expect(page.getByTestId("verdict-reasons")).toContainText(/visibly not done/i);
  await expect(page.getByTestId("alert-wrong_order")).toBeVisible();

  const before = await page.getByTestId("video-position").innerText();
  await page.getByTestId("alert-evidence").first().click();
  await expect
    .poll(async () => page.getByTestId("video-position").innerText(), {
      timeout: 15_000,
    })
    .not.toBe(before);
  await page.screenshot({ path: path.join(SHOTS, "06-not-verified.png"), fullPage: true });

  // 3. An obscured attempt is inconclusive, not a failure.
  await runAttempt(page, skillId, "uncertain.webm");
  await expect(page.getByTestId("verdict-INCONCLUSIVE")).toBeVisible();
  await expect(page.getByTestId("verdict-NOT_VERIFIED")).toHaveCount(0);
  await expect(page.getByTestId("verdict-reasons")).toContainText(
    /never confirmed|cannot establish|not observed absent/i,
  );
  await page.screenshot({ path: path.join(SHOTS, "07-inconclusive.png"), fullPage: true });

  // 4. A real correction ends verified.
  await runAttempt(page, skillId, "corrected.webm");
  await expect(page.getByTestId("verdict-VERIFIED")).toBeVisible();
  await expect(page.getByTestId("verdict-reasons")).toContainText(/corrected/i);
  await page.screenshot({ path: path.join(SHOTS, "08-corrected.png"), fullPage: true });

  // 5. A different valid order is also verified.
  await runAttempt(page, skillId, "alternate_order.webm");
  await expect(page.getByTestId("verdict-VERIFIED")).toBeVisible();

  // The library shows the published skill and its latest verdict.
  await page.goto("/");
  await expect(page.getByTestId("skill-card").first()).toContainText("LED");
});

test("demo mode is labelled MOCK and runs the loop offline", async ({ page }) => {
  await page.goto("/#/demo");
  await expect(page.getByTestId("demo-banner")).toContainText("Demo Mode");
  await expect(
    page.getByTestId("demo-banner").getByTestId("provenance-badge"),
  ).toContainText("MOCK");

  await page.getByTestId("demo-teach").click();
  await expect(page.getByTestId("demo-publish")).toBeVisible({ timeout: 90_000 });
  await page.getByTestId("demo-publish").click();
  await expect(page.getByTestId("demo-run-wrong_order")).toBeEnabled({
    timeout: 30_000,
  });
  await page.screenshot({ path: path.join(SHOTS, "09-demo.png"), fullPage: true });

  await page.getByTestId("demo-run-wrong_order").click();
  await expect(page.getByTestId("demo-see-result")).toBeVisible({ timeout: 90_000 });
  await page.getByTestId("demo-see-result").click();
  await expect(page.getByTestId("verdict-NOT_VERIFIED")).toBeVisible();
  await expect(page.getByTestId("verdict-panel")).toContainText("MOCK");
});

test("the app is usable at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByTestId("cta-teach")).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({ path: path.join(SHOTS, "10-mobile.png"), fullPage: true });
});
