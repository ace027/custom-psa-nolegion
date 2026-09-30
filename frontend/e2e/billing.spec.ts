import { expect, test } from "@playwright/test";

// Requires a FRESHLY seeded database (python -m app.seed): it starts and finalizes the run for
// the current month, which can only happen once per month.
test("monthly billing run: build, review, adjust, re-review, finalize, PDF", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("billing@example.com");
  await page.getByRole("button", { name: "Dev login" }).click();
  await page.getByRole("link", { name: "Billing" }).click();
  await expect(page.getByRole("heading", { name: "Billing" })).toBeVisible();

  // start the run for the current month
  await page.getByRole("button", { name: "Start billing run" }).click();
  await expect(page.getByRole("heading", { name: /Billing run \d{4}-\d{2}/ })).toBeVisible();
  for (const client of ["Contoso Dental", "Fabrikam Engineering", "Northwind Legal"]) {
    await expect(page.getByRole("cell", { name: client })).toBeVisible();
  }

  // review it, then adjust a draft: the review must be undone
  await page.getByRole("button", { name: "Mark reviewed" }).click();
  await expect(page.getByRole("button", { name: "Finalize all invoices" })).toBeVisible();
  await page.getByRole("link", { name: "draft" }).first().click();
  await page.getByLabel("Line description").last().waitFor();
  await page.getByLabel("Add a line (or a credit)").fill("Goodwill credit");
  await page.getByLabel("Unit price ($)").fill("-10.00");
  await page.getByRole("button", { name: "Add line" }).click();
  await expect(page.getByText("-$10.00").first()).toBeVisible();
  await page.getByRole("link", { name: "Billing run" }).click();
  await expect(page.getByRole("button", { name: "Mark reviewed" })).toBeVisible(); // review was invalidated

  // review again and finalize everything
  await page.getByRole("button", { name: "Mark reviewed" }).click();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Finalize all invoices" }).click();
  await expect(page.getByText("finalized").first()).toBeVisible();
  const links = page.getByRole("link", { name: /^INV-\d{4}-\d{4}$/ });
  await expect(links).toHaveCount(3);
  const numbers = await links.allInnerTexts();
  expect(numbers).toHaveLength(3);
  expect(new Set(numbers).size).toBe(3);

  // a finalized invoice is frozen and has a PDF
  await page.getByRole("link", { name: numbers[0] }).click();
  await expect(page.getByText(/This invoice is frozen/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Add line" })).toHaveCount(0);
  const href = await page.getByRole("link", { name: "Download PDF" }).getAttribute("href");
  const pdf = await page.request.get(href!);
  expect(pdf.status()).toBe(200);
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
  expect((await pdf.body()).subarray(0, 4).toString()).toBe("%PDF");

  // ---- payments: record a payment against this invoice, see it paid, and see receivables move ----
  await page.goto(page.url()); // stay on the finalized invoice
  await expect(page.getByText("unpaid").first()).toBeVisible();
  await page.getByRole("link", { name: "Record payment" }).first().click();
  await expect(page.getByRole("heading", { name: "Record a payment" })).toBeVisible();
  await page.getByLabel("Reference (check #, ACH id)").fill("E2E-1001");
  await expect(page.getByText("Fully applied.")).toBeVisible(); // prefilled from the invoice balance
  await page.getByRole("button", { name: "Record payment" }).click();
  await expect(page.getByRole("cell", { name: "E2E-1001" })).toBeVisible();

  await page.getByRole("link", { name: "Invoices" }).click();
  await page.getByLabel("Payment").selectOption("paid");
  await expect(page.getByRole("link", { name: numbers[0] })).toBeVisible();
  await page.getByLabel("Payment").selectOption("open");
  await expect(page.getByRole("link", { name: numbers[0] })).toHaveCount(0);

  await page.getByRole("link", { name: /^Receivables/ }).click();
  await expect(page.getByRole("heading", { name: "Billing" })).toBeVisible();
  await expect(page.getByText("Outstanding", { exact: true })).toBeVisible();
});
