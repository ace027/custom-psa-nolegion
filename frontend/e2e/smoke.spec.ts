import { expect, test } from "@playwright/test";

// Requires seeded data (python -m app.seed) and DEV_LOGIN_ENABLED=true on the API.
test("sign in, browse and edit an organization, see it in the audit log", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByRole("button", { name: "Dev login" }).click();

  await expect(page.getByRole("heading", { name: "Organizations" })).toBeVisible();
  await page.getByRole("link", { name: "Contoso Dental" }).click();
  await expect(page.getByRole("heading", { name: "Contoso Dental" })).toBeVisible();
  await expect(page.getByText("Dana Contoso")).toBeVisible();

  const notes = `smoke-${Date.now()}`;
  await page.getByLabel("Notes").fill(notes);
  await page.getByRole("button", { name: "Save" }).click();

  await page.getByRole("link", { name: "Audit log" }).click();
  await expect(page.getByText("organization.update").first()).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByText("Sign in with Microsoft")).toBeVisible();
});
