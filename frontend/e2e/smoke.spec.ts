import { expect, test } from "@playwright/test";

// Requires seeded data (python -m app.seed) and DEV_LOGIN_ENABLED=true on the API.
test("sign in, browse and edit an organization, see it in the audit log", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByRole("button", { name: "Dev login" }).click();

  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible(); // landing page
  await page.getByRole("link", { name: "Organizations" }).click();
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

test("ticket lifecycle: create, note, time (rounded up), status, dashboard", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("tech@example.com");
  await page.getByRole("button", { name: "Dev login" }).click();
  await page.getByRole("link", { name: "Tickets" }).click();

  const subject = `E2E ticket ${Date.now()}`;
  await page.getByLabel("Organization").selectOption({ label: "Contoso Dental" });
  await page.getByLabel("Subject", { exact: true }).fill(subject);
  await page.getByRole("button", { name: "Create ticket" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(subject) })).toBeVisible();

  await page.getByLabel("Add a note").fill("Internal: looks like DNS");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByText("Internal: looks like DNS")).toBeVisible();

  await page.getByLabel("Work type").selectOption({ label: "Remote" });
  await page.getByLabel("Minutes").fill("20");
  await page.getByRole("button", { name: "Log time" }).click();
  await expect(page.getByText("20 min")).toBeVisible(); // actual
  await expect(page.getByText("30 min").first()).toBeVisible(); // billable: 20 rounds UP to 30

  await page.getByLabel("Status").selectOption({ label: "Resolved" });
  await expect(page.getByLabel("Status")).toHaveValue("resolved");

  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText(subject)).toHaveCount(0); // resolved tickets leave the open lists
});
