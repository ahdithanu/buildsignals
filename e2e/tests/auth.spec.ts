import { test, expect } from "@playwright/test";
import { PASSWORD, uniqueEmail, registerAndLogin, signOut } from "./helpers";

/**
 * Auth happy paths. The most stable E2E — the login/register forms use
 * fixed element ids (#email, #password, #fullName, #orgName) so these
 * selectors should survive restyling.
 *
 */

test("register lands on the authenticated dashboard", async ({ page }) => {
  await registerAndLogin(page, uniqueEmail());
  await expect(
    page.getByRole("heading", { name: "Dashboard" }).first(),
  ).toBeVisible();
});

test("log out then log back in", async ({ page }) => {
  const email = uniqueEmail();
  await registerAndLogin(page, email);

  await signOut(page);

  await page.locator("#email").fill(email);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();

  await expect(page).toHaveURL("http://localhost:8080/");
  await expect(
    page.getByRole("heading", { name: "Dashboard" }).first(),
  ).toBeVisible();
});

test("bad password is rejected", async ({ page }) => {
  const email = uniqueEmail();
  await registerAndLogin(page, email);
  await signOut(page);

  await page.locator("#email").fill(email);
  await page.locator("#password").fill("wrong-password");
  const rejected = page.waitForResponse(response => response.url().endsWith("/auth/login") && response.request().method() === "POST");
  await page.getByRole("button", { name: /sign in/i }).click();
  expect((await rejected).status()).toBe(401);
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});
