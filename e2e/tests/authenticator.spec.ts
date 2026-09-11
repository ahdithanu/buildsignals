import { spawn } from "node:child_process";
import { test, expect } from "@playwright/test";
import { PASSWORD, uniqueEmail, registerAndLogin, signOut } from "./helpers";

// Even synthetic enrollment keys should not be retained in traces/screenshots.
test.use({ trace: "off", screenshot: "off", video: "off" });

function authenticatorCode(secret: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON || "python3", ["-c",
      "import sys, pyotp; print(pyotp.TOTP(sys.stdin.read().strip()).now())"],
    { stdio: ["pipe", "pipe", "ignore"] });
    let result = "";
    child.stdout.on("data", chunk => { result += String(chunk); });
    child.on("error", () => reject(new Error("Local test authenticator failed")));
    child.on("close", code => {
      if (code === 0 && /^[0-9]{6}$/.test(result.trim())) resolve(result.trim());
      else reject(new Error("Local test authenticator failed"));
    });
    child.stdin.end(secret);
  });
}

for (const width of [390, 768, 1440]) {
  test(`authenticator enrollment, enforced login and disable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const email = uniqueEmail();
    await registerAndLogin(page, email);
    await page.goto("/account");
    const section = page.getByRole("region", { name: "Authenticator", exact: true });
    await expect(section.getByText("Not enabled", { exact: true })).toBeVisible();
    await section.getByRole("button", { name: "Set up authenticator", exact: true }).click();
    const key = section.getByLabel("Manual setup key");
    await expect(key).toBeVisible();
    let secret = await key.inputValue();
    expect(/^[A-Z2-7]{16,64}$/.test(secret)).toBe(true);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    await section.getByLabel("Authenticator code", { exact: true }).fill(await authenticatorCode(secret));
    await section.getByRole("button", { name: "Confirm authenticator", exact: true }).click();
    await expect(section.getByText("Enabled", { exact: true })).toBeVisible();
    await expect(key).toHaveCount(0);
    expect(await page.evaluate(value => [...Object.values(localStorage), ...Object.values(sessionStorage)].some(item => item.includes(value)), secret)).toBe(false);

    await signOut(page);
    await page.locator("#email").fill(email);
    await page.locator("#password").fill(PASSWORD);
    const denied = page.waitForResponse(response => response.url().endsWith("/auth/login") && response.request().method() === "POST");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    expect((await denied).status()).toBe(401);
    await expect(page).toHaveURL(/\/login$/);
    await page.getByLabel("Authenticator code", { exact: true }).fill(await authenticatorCode(secret));
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL("http://localhost:8080/");

    await page.goto("/account");
    await section.getByRole("button", { name: "Disable authenticator", exact: true }).click();
    await section.getByLabel("Current password", { exact: true }).fill(PASSWORD);
    await section.getByLabel("Authenticator code", { exact: true }).fill(await authenticatorCode(secret));
    await section.getByRole("button", { name: "Confirm disable", exact: true }).click();
    await expect(section.getByText("Not enabled", { exact: true })).toBeVisible();
    secret = "";
    await page.reload();
    await expect(section.getByText("Not enabled", { exact: true })).toBeVisible();
  });
}
