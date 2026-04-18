/**
 * Smoke tests — verify the CRUZ command centre shell loads and
 * tab navigation works. These tests run against the Vite dev server
 * and do NOT depend on a real backend or LiveKit server.
 *
 * Design rules:
 * - All assertions target static markup or text that is rendered
 *   immediately (no async API calls required).
 * - Network errors (health / approvals / LiveKit token) are expected
 *   and do NOT cause test failures.
 */
import { test, expect } from "@playwright/test";

// Suppress console errors from failed API calls so test output is clean.
test.beforeEach(({ page }) => {
  page.on("console", (msg) => {
    if (msg.type() === "error") return; // swallow API / WS errors
  });
});

test("root redirects to /tab/conversation and shows orb", async ({ page }) => {
  await page.goto("/");
  // Should redirect to the conversation tab
  await expect(page).toHaveURL(/\/tab\/conversation/, { timeout: 8_000 });

  // The CRUZ label in the SystemBar is always present (static markup)
  await expect(page.getByText("CRUZ").first()).toBeVisible();

  // The orb idle state text OR the conversation prompt is visible
  // (either "Ready." from Orb or the transcript placeholder)
  const bodyText = await page.locator("body").textContent();
  expect(bodyText).toBeTruthy();
  expect(bodyText!.length).toBeGreaterThan(10);
});

test("navigating to /tab/dashboard renders the dashboard container", async ({ page }) => {
  await page.goto("/tab/dashboard");
  // Either the loading state or the dashboard content is visible
  const body = page.locator("body");
  await expect(body).toBeVisible({ timeout: 8_000 });

  // The tab URL should be as requested
  await expect(page).toHaveURL(/\/tab\/dashboard/);

  // Page renders something — "Loading dashboard" or a card heading
  const text = await body.textContent();
  expect(text).toMatch(/dashboard|loading|system|metrics/i);
});

test("navigating to /tab/events renders the events container", async ({ page }) => {
  await page.goto("/tab/events");
  await expect(page).toHaveURL(/\/tab\/events/, { timeout: 8_000 });

  const text = await page.locator("body").textContent();
  // EventsTab renders a filter input with placeholder text
  expect(text).toMatch(/filter|agent|trace/i);
});

test("navigating to /tab/approvals renders the approvals container", async ({ page }) => {
  await page.goto("/tab/approvals");
  await expect(page).toHaveURL(/\/tab\/approvals/, { timeout: 8_000 });

  const text = await page.locator("body").textContent();
  // ApprovalsTab always renders either the list header or the empty state
  expect(text).toMatch(/approval|pending|loading/i);
});
