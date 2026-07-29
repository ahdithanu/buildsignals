import { test, expect } from "@playwright/test";
import { uniqueEmail, registerAndLogin } from "./helpers";

/**
 * Create-a-deal happy path through the AddDealModal.
 *
 * ⚠️ MORE FRAGILE than auth.spec — the modal's Asset Type / Market fields are
 * radix <Select> components (role="combobox" trigger + role="option" items in
 * a portal), which are the most likely selectors to need adjustment on the
 * first real run. The text inputs (#deal-name etc.) are stable.
 *
 * Selectors read from src/components/AddDealModal.tsx and
 * src/pages/DealInbox.tsx. Asset types: Multifamily/Retail/Industrial/Mixed
 * Use. Markets include "Austin, TX".
 */

test("create a deal and see it in the inbox list", async ({ page }) => {
  await registerAndLogin(page, uniqueEmail());

  // The deal list + "Add Deal" button live on /inbox (DealInbox.tsx).
  await page.goto("/inbox");

  const dealName = `E2E Deal ${Date.now()}`;

  // Two "Add Deal" triggers exist (header + empty state); either opens the
  // same modal. Take the first that's visible.
  await page.getByRole("button", { name: /add deal/i }).first().click();

  // Modal text inputs — stable ids.
  await page.locator("#deal-name").fill(dealName);
  await page.locator("#deal-address").fill("123 Main St");
  await page.locator("#deal-price").fill("3500000");
  await page.locator("#deal-source").fill("E2E");

  // Radix Select #1 (Asset Type) and #2 (Market), in DOM order.
  const comboboxes = page.getByRole("combobox");
  await comboboxes.nth(0).click();
  await page.getByRole("option", { name: "Multifamily" }).click();
  await comboboxes.nth(1).click();
  await page.getByRole("option", { name: "Austin, TX" }).click();

  // Submit — the modal's submit button reads "Add Deal".
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /add deal/i })
    .click();

  // The new deal should appear in the list.
  await expect(page.getByRole("cell", { name: dealName })).toBeVisible();
});
