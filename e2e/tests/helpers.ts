import { Page, expect } from "@playwright/test";

export const PASSWORD = "E2ePassw0rd!";

/** Unique email per run so re-runs don't collide on "already registered". */
export function uniqueEmail(): string {
  const rand = Math.random().toString(36).slice(2, 10);
  return `e2e-${rand}@example.com`;
}

/** Register a fresh user + org and land on the authenticated dashboard. */
export async function registerAndLogin(page: Page, email: string): Promise<void> {
  await page.goto("/register");
  await page.locator("#fullName").fill("E2E Tester");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(PASSWORD);
  await page.locator("#orgName").fill(`E2E Org ${Date.now()}`);
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page.getByRole("alert")).not.toBeVisible({ timeout: 2_000 }).catch(() => undefined);
  await expect(page).toHaveURL("http://localhost:8080/", { timeout: 15_000 });
}
