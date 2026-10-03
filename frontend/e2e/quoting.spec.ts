import { Browser, expect, test } from "@playwright/test";

// Requires seeded data (python -m app.seed) and DEV_LOGIN_ENABLED=true on the API.
async function signIn(browser: Browser, email: string, viewport?: { width: number; height: number }) {
  const ctx = await browser.newContext({ viewport });
  const page = await ctx.newPage();
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Dev login" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  return page;
}

test("quote a prospect: survey on a phone, adjusted price, approval, acceptance, agreement", async ({ browser }) => {
  const name = `Prospect ${Date.now()}`;

  // admin sets the rate card
  const admin = await signIn(browser, "admin@example.com");
  await admin.getByRole("link", { name: "Quotes" }).click();
  await admin.getByRole("link", { name: "Rate card" }).click();
  const inputs = admin.locator("fieldset").first().locator("input");
  await inputs.nth(0).fill("100.00"); // per user
  await inputs.nth(1).fill("20.00"); // per workstation
  await inputs.nth(2).fill("100.00"); // per server
  await admin.getByRole("button", { name: "Save rate card" }).click();
  await expect(admin.getByText("Saved.")).toBeVisible();

  // tech fills the survey on a phone-sized screen
  const tech = await signIn(browser, "tech@example.com", { width: 390, height: 844 });
  await tech.getByRole("link", { name: "Quotes" }).click();
  await tech.getByLabel("Prospect name").fill(name);
  await tech.getByRole("button", { name: "Schedule survey" }).click();
  await expect(tech.getByRole("heading", { name: `Site survey: ${name}` })).toBeVisible();
  await tech.getByLabel("Users").fill("10");
  for (let i = 0; i < 5; i++) await tech.getByRole("button", { name: "+ Workstation" }).click();
  await tech.getByRole("button", { name: "+ Server" }).click();
  for (let i = 1; i <= 5; i++) {
    const card = tech.getByLabel(`Device ${i}`);
    await card.getByLabel("Warranty (if no date)").selectOption(i <= 4 ? "out_of_warranty" : "in_warranty");
  }
  await tech.getByLabel("Device 6").getByLabel("Warranty (if no date)").selectOption("in_warranty");
  await expect(tech.getByText("Devices (6 priced, 4 out of warranty or unknown)")).toBeVisible();
  tech.once("dialog", (d) => d.accept());
  await tech.getByRole("button", { name: "Save and complete" }).click();
  await tech.getByRole("button", { name: "Create quote" }).click();

  // 10*$100 + 5*$20 + 1*$100 = $1,200 base; 4 of 6 out of warranty -> +25% = $1,500
  await expect(tech.getByTestId("price")).toHaveText("$1,500.00");
  await expect(tech.getByText(/4 of 6 priced devices \(67%\) are out of warranty/)).toBeVisible();
  await tech.getByLabel("New monthly price").fill("1400.00");
  await tech.getByLabel(/Reason/).fill("Referral discount");
  await tech.getByRole("button", { name: "Apply" }).click();
  await expect(tech.getByTestId("price")).toHaveText("$1,400.00");
  await tech.getByRole("button", { name: "Submit for approval" }).click();
  await expect(tech.getByText("Waiting for an admin to approve")).toBeVisible();
  await expect(tech.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
  const quoteUrl = tech.url();

  // admin approves, sends, records acceptance
  await admin.goto(quoteUrl);
  await admin.getByRole("button", { name: "Approve", exact: true }).click();
  await admin.getByRole("button", { name: "Mark as sent and lock" }).click();
  await expect(admin.getByText("Sent. Record the client's answer")).toBeVisible();
  await admin.getByRole("button", { name: "Client accepted" }).click();
  await expect(admin.getByText("Agreement created.")).toBeVisible();

  await admin.getByRole("link", { name: "Billing > Agreements" }).click();
  await expect(admin.getByRole("row", { name: new RegExp(`${name}.*Flat fee.*\\$1,400\\.00`) })).toBeVisible();
});
