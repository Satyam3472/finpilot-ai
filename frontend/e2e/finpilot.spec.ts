import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";

async function screenshot(page: Page, filename: string) {
  if (process.env.FINPILOT_CAPTURE_SCREENSHOTS !== "1") return;
  const directory = resolve(process.cwd(), "../docs/screenshots");
  mkdirSync(directory, { recursive: true });
  await page.screenshot({
    path: resolve(directory, filename), fullPage: true, animations: "disabled",
    style: "[data-sonner-toaster] { visibility: hidden; }",
  });
}

test.beforeEach(async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Password").fill(process.env.FINPILOT_E2E_PASSWORD!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard", exact: true })).toBeVisible();
});

test("protects finance data and revokes the session on sign-out", async ({ page }) => {
  expect(await (await page.request.get("/api/health/ready")).json()).toEqual({ status: "ready" });
  await expect((await page.request.get("/api/run")).status()).toBe(404);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in to FinPilot" })).toBeVisible();
  expect((await page.request.get("/api/transactions")).status()).toBe(401);
  await page.goto("/budgets");
  await expect(page.getByRole("heading", { name: "Sign in to FinPilot" })).toBeVisible();
});

test("imports a real fixture, updates dashboards and budgets, and explains missing months", async ({ page }) => {
  await page.goto("/imports");
  await expect(page.getByRole("heading", { name: "No import history" })).toBeVisible();
  await page.getByLabel("Statement file").setInputFiles({
    name: "invalid.txt", mimeType: "text/plain", buffer: Buffer.from("unsupported"),
  });
  await expect(page.getByRole("alert").filter({ hasText: "Choose a CSV or XLSX file." })).toBeVisible();

  const statement = resolve(process.cwd(), "../sample_data/analytics_statement.csv");
  await page.getByLabel("Statement file").setInputFiles(statement);
  await page.getByRole("button", { name: "Import statement", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Import summary" })).toBeVisible();
  await expect(page.getByLabel("Import counts")).toContainText("24");
  await expect(page.getByRole("row", { name: /analytics_statement.csv/ })).toContainText("Imported");

  await page.getByLabel("Statement file").setInputFiles(statement);
  await page.getByRole("button", { name: "Import statement", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Statement already imported" })).toBeVisible();
  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await expect(page.locator(".metric").filter({ hasText: "Total expenses" })).toContainText("₹5,312");
  await expect(page.locator(".metric").filter({ hasText: "Total income" })).toContainText("₹60,000");
  await expect(page.locator(".metric").filter({ hasText: "Net cash flow" })).toContainText("₹54,688");
  await page.getByRole("link", { name: "View transactions" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Transactions" })).toBeVisible();
  await page.getByRole("combobox", { name: "Category", exact: true }).selectOption("food");
  await page.getByRole("textbox", { name: "Search" }).fill("swiggy");
  await expect(page.getByRole("row", { name: /Swiggy/i })).toContainText("₹2,000");
  await expect(page.getByRole("row", { name: /Zomato/i })).toHaveCount(0);

  await page.getByRole("link", { name: "Budgets", exact: true }).click();
  await expect(page.getByRole("heading", { name: "No budgets for this month" })).toBeVisible();
  await page.getByRole("button", { name: "New budget" }).click();
  await page.getByRole("dialog").getByRole("combobox", { name: "Category", exact: true }).selectOption("food");
  await page.getByLabel("Amount (INR)").fill("-1");
  await page.getByRole("button", { name: "Save budget" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Enter a nonnegative amount");
  await page.getByLabel("Amount (INR)").fill("2000");
  await page.getByRole("button", { name: "Save budget" }).click();
  await expect(page.getByRole("progressbar", { name: "Food budget used" })).toHaveAttribute("aria-valuetext", "105.6%");
  await expect(page.getByText("Over budget", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await expect(page.getByText("Over budget", { exact: true })).toBeVisible();
  await expect(page.getByRole("group", { name: "Historical cash flow chart" })).toBeVisible();
  await screenshot(page, "dashboard.png");

  await page.getByRole("link", { name: "Budgets", exact: true }).click();
  await page.getByRole("button", { name: "Edit food budget" }).click();
  await page.getByLabel("Amount (INR)").fill("2500.25");
  await page.getByRole("button", { name: "Save budget" }).click();
  await expect(page.locator(".budget-allocation")).toContainText("₹2,500.25");
  await page.reload();
  await expect(page.locator(".budget-allocation")).toContainText("₹2,500.25");
  await page.getByRole("button", { name: "Delete food budget" }).click();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.locator(".budget-allocation")).toContainText("₹2,500.25");
  await page.getByRole("button", { name: "Delete food budget" }).click();
  await page.getByRole("button", { name: "Delete budget", exact: true }).click();
  await expect(page.getByRole("heading", { name: "No budgets for this month" })).toBeVisible();

  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await page.getByLabel("Dashboard month").fill("2026-08");
  await expect(page.getByText(/No imported records for August 2026/)).toBeVisible();
  await expect(page.locator(".metric").filter({ hasText: "Total expenses" })).toContainText("—");
  await page.getByRole("link", { name: "Analytics", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Unusual expense candidates" })).toBeVisible();
  await expect(page.getByRole("row", { name: /Food.*₹2,000/ })).toBeVisible();
  await screenshot(page, "analytics.png");
  await page.getByLabel("Baseline month", { exact: true }).fill("2026-08");
  await expect(page.getByRole("heading", { name: "Comparison unavailable" })).toBeVisible();
  await expect(page.getByText(/No imported records for August 2026/)).toBeVisible();
});

test("assistant shows progress, restores the selected conversation, and reports a failed reply", async ({ page }) => {
  const id = "52a6fb15-63a6-4eb0-9e39-d3a531ef5c65";
  const question = "What were my October 2026 expenses?";
  const reply = "Your imported October 2026 expenses were ₹5,312. <img src=x onerror=alert(1)>";
  const session = { id, title: question, updated_at: 100 };
  const cors = {
    "access-control-allow-origin": "http://127.0.0.1:3000",
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "content-type",
  };
  let complete = false;
  let fail = false;
  let finishReply: () => void = () => {};
  const waiting = new Promise<void>((resolve) => { finishReply = resolve; });

  await page.route(/\/api\/chat\/sessions(?:\/.*)?$/, async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: cors });
    } else if (pathname.endsWith("/messages")) {
      if (fail) {
        await route.fulfill({ headers: cors, contentType: "text/event-stream",
          body: 'event: error\ndata: {"message":"The assistant is unavailable."}\n\n' });
      } else {
        await waiting;
        complete = true;
        await route.fulfill({ headers: cors, contentType: "text/event-stream",
          body: `event: delta\ndata: ${JSON.stringify({ text: reply })}\n\nevent: done\ndata: ${JSON.stringify({ text: reply })}\n\n` });
      }
    } else if (pathname.endsWith(id)) {
      await route.fulfill({ headers: cors, json: { ...session, messages: complete ?
        [{ role: "user", text: question }, { role: "assistant", text: reply }] : [] } });
    } else if (request.method() === "POST") {
      await route.fulfill({ status: 201, headers: cors, json: session });
    } else {
      await route.fulfill({ headers: cors, json: complete ? [session] : [] });
    }
  });

  await page.goto("/assistant");
  await expect(page.getByRole("heading", { name: "What would you like to explore?" })).toBeVisible();
  await page.getByRole("textbox", { name: "Message FinPilot" }).fill(question);
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByRole("status").filter({ hasText: "preparing a reply" })).toBeVisible();
  finishReply();
  await expect(page.getByText(reply, { exact: true })).toBeVisible();
  await expect(page.locator(".message-assistant img")).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(id));
  await page.reload();
  await expect(page.getByText(reply, { exact: true })).toBeVisible();

  fail = true;
  await page.getByRole("textbox", { name: "Message FinPilot" }).fill("Try again?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByRole("region", { name: "Assistant conversation" }).getByRole("alert"))
    .toContainText("The assistant is unavailable.");
  await expect(page.getByRole("textbox", { name: "Message FinPilot" })).toHaveValue("Try again?");
});

test("mobile navigation opens an accessible drawer without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open navigation" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.getByRole("button", { name: "Open navigation" }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByRole("heading", { name: "FinPilot AI" })).toBeVisible();
  await drawer.getByRole("link", { name: "Transactions" }).click();
  await expect(drawer).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1, name: "Transactions" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});
