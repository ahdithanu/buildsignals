import { test, expect } from "@playwright/test";
import { PASSWORD, uniqueEmail, registerAndLogin } from "./helpers";

/**
 * Auth happy paths. The most stable E2E — the login/register forms use
 * fixed element ids (#email, #password, #fullName, #orgName) so these
 * selectors should survive restyling.
 *
 * ⚠️ Never executed yet — see e2e/README.md. Selectors were read from
 * src/pages/Login.tsx and Register.tsx.
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

  // Layout.tsx renders the sign-out control with aria-label="Sign out".
  await page.getByRole("button", { name: "Sign out" }).click();

  await page.goto("/login");
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
  await page.getByRole("button", { name: "Sign out" }).click();

  await page.goto("/login");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill("wrong-password");
  await page.getByRole("button", { name: /sign in/i }).click();

  // Should stay on /login. Exact error copy may need adjusting on first run;
  // the URL assertion is the stable part.
  await expect(page).toHaveURL(/\/login$/);
});
