import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Requires seeded data (python -m app.seed) and DEV_LOGIN_ENABLED=true on the API: run it with scripts/e2e.sh.
// The clock is pinned to Tuesday 2030-01-08 15:00 UTC, which is 09:00 in America/Chicago (the seeded org zone;
// the tests read the zone from /api/settings and never assume it). Bookings are on that day, in the future.
const DAY = "2030-01-08";
const NOW = new Date(`${DAY}T15:00:00Z`);
const HEADERS = { "X-Requested-With": "psa" };

test.use({ viewport: { width: 1400, height: 1000 } });

/* ---- helpers ---- */

function offsetMs(ts: number, zone: string): number {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", { timeZone: zone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })
      .formatToParts(new Date(ts)).map((x) => [x.type, x.value]),
  );
  return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second) - Math.floor(ts / 1000) * 1000;
}
/** UTC instant of a wall-clock time in `zone`. */
function zoned(day: string, hm: string, zone: string): string {
  const [y, m, d] = day.split("-").map(Number);
  const [h, mi] = hm.split(":").map(Number);
  const wall = Date.UTC(y, m - 1, d, h, mi);
  let ts = wall;
  for (let i = 0; i < 3; i++) ts = wall - offsetMs(ts, zone);
  return new Date(ts).toISOString();
}

async function login(page: Page, email: string): Promise<void> {
  await page.clock.setFixedTime(NOW);
  await page.goto("/");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Dev login" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

interface Staff { id: number; email: string; display_name: string }
interface Appt { id: number; tech_id: number; starts_at: string; ends_at: string; status: string }

async function get<T>(request: APIRequestContext, path: string): Promise<T> {
  const res = await request.get(`/api${path}`);
  expect(res.ok(), `${path}: ${res.status()}`).toBeTruthy();
  return res.json();
}
async function post<T>(request: APIRequestContext, path: string, data: unknown): Promise<T> {
  const res = await request.post(`/api${path}`, { data, headers: HEADERS });
  expect(res.ok(), `${path}: ${res.status()} ${await res.text()}`).toBeTruthy();
  return res.json();
}

async function setup(page: Page) {
  const request = page.request;
  const zone = (await get<{ timezone: string }>(request, "/settings")).timezone;
  const users = await get<Staff[]>(request, "/users");
  const tech = users.find((u) => u.email === "tech@example.com")!;
  const admin = users.find((u) => u.email === "admin@example.com")!;
  const orgs = await get<{ items: { id: number; name: string }[] }>(request, "/organizations?limit=200");
  const org = orgs.items.find((o) => o.name === "Contoso Dental") ?? orgs.items[0];
  const newTicket = (label: string) =>
    post<{ id: number; number: number }>(request, "/tickets", { organization_id: org.id, subject: `E2E dispatch ${label} ${Date.now()}` });
  const book = async (ticketId: number, techId: number, start: string, end: string) =>
    post<Appt>(request, "/appointments", { ticket_id: ticketId, tech_id: techId, starts_at: zoned(DAY, start, zone), ends_at: zoned(DAY, end, zone) });
  return { request, zone, tech, admin, newTicket, book };
}

/** Cancel what a test booked, so repeated runs on the same database start from the same board. */
async function cancelAll(request: APIRequestContext, ids: number[]): Promise<void> {
  for (const id of ids) await request.post(`/api/appointments/${id}/cancel`, { data: { reason: "e2e cleanup" }, headers: HEADERS });
}

const event = (page: Page, number: number) => page.locator(".rbc-event", { hasText: `#${number}` });
const toast = (page: Page) => page.getByRole("status").filter({ has: page.getByRole("button", { name: "Undo" }) });

/* ---- tests ---- */

test("book from the ticket, see it on the board, edit it, undo", async ({ page }) => {
  await login(page, "admin@example.com");
  const s = await setup(page);
  const ticket = await s.newTicket("booking");
  const created: number[] = [];
  try {
    await page.goto(`/tickets/${ticket.id}`);
    const card = page.locator("section", { has: page.getByRole("heading", { name: "Appointments", exact: true }) });
    await expect(card.getByText("No appointments.")).toBeVisible();
    await card.getByRole("button", { name: "Book", exact: true }).click();

    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Tech").selectOption({ label: s.tech.display_name });
    await dialog.getByLabel("Date").fill(DAY);
    await dialog.getByLabel("Start").fill("10:00");
    await dialog.getByLabel("End").fill("11:00");
    await dialog.getByRole("button", { name: "Book", exact: true }).click();
    await expect(dialog).toBeHidden();

    await expect(card.getByText(s.tech.display_name)).toBeVisible();
    const [appt] = (await get<Appt[]>(s.request, `/appointments?ticket_id=${ticket.id}`));
    created.push(appt.id);
    expect(appt.tech_id).toBe(s.tech.id);
    expect(Date.parse(appt.starts_at)).toBe(Date.parse(zoned(DAY, "10:00", s.zone)));
    expect(Date.parse(appt.ends_at)).toBe(Date.parse(zoned(DAY, "11:00", s.zone)));

    await card.getByRole("link", { name: "Open on board" }).click();
    await expect(page).toHaveURL(new RegExp(`/dispatch\\?view=day&date=${DAY}`));
    const block = event(page, ticket.number);
    await expect(block).toBeVisible();

    // The event sits in the booked tech's column.
    const header = await page.locator(".rbc-row-resource .rbc-header", { hasText: s.tech.display_name }).boundingBox();
    const box = (await block.boundingBox())!;
    expect(header).not.toBeNull();
    expect(box.x + box.width / 2).toBeGreaterThan(header!.x);
    expect(box.x + box.width / 2).toBeLessThan(header!.x + header!.width);

    await block.click();
    const edit = page.getByRole("dialog");
    await edit.getByLabel("Start").fill("13:00");
    await edit.getByLabel("End").fill("14:00");
    await edit.getByRole("button", { name: "Save" }).click();
    await expect(toast(page)).toContainText("13:00");
    expect(Date.parse((await get<Appt>(s.request, `/appointments/${appt.id}`)).starts_at)).toBe(Date.parse(zoned(DAY, "13:00", s.zone)));

    await toast(page).getByRole("button", { name: "Undo" }).click();
    await expect(page.getByRole("status")).toContainText("Change undone");
    const back = await get<Appt>(s.request, `/appointments/${appt.id}`);
    expect(Date.parse(back.starts_at)).toBe(Date.parse(zoned(DAY, "10:00", s.zone)));
    expect(Date.parse(back.ends_at)).toBe(Date.parse(zoned(DAY, "11:00", s.zone)));
  } finally {
    await cancelAll(s.request, created);
  }
});

test("reassigning onto a busy tech shows the conflict", async ({ page }) => {
  await login(page, "admin@example.com");
  const s = await setup(page);
  const [t1, t2] = [await s.newTicket("reassign A"), await s.newTicket("reassign B")];
  const a1 = await s.book(t1.id, s.tech.id, "10:00", "11:00");
  const a2 = await s.book(t2.id, s.admin.id, "10:00", "11:00");
  try {
    await page.goto(`/dispatch?view=day&date=${DAY}`);
    await expect(event(page, t1.number)).toBeVisible();
    await expect(event(page, t2.number)).toBeVisible();
    await event(page, t1.number).click();
    const edit = page.getByRole("dialog");
    await edit.getByLabel("Tech").selectOption({ label: s.admin.display_name });
    await edit.getByRole("button", { name: "Save" }).click();

    await expect(toast(page)).toContainText("Overlaps another appointment");
    await expect(event(page, t1.number).getByLabel("Has conflicts")).toBeVisible();
    expect((await get<Appt>(s.request, `/appointments/${a1.id}`)).tech_id).toBe(s.admin.id);
  } finally {
    await cancelAll(s.request, [a1.id, a2.id]);
  }
});

test("drag an event one hour later", async ({ page }) => {
  await login(page, "admin@example.com");
  const s = await setup(page);
  const t = await s.newTicket("drag");
  const a = await s.book(t.id, s.tech.id, "10:00", "11:00");
  try {
    await page.goto(`/dispatch?view=day&date=${DAY}`);
    const block = event(page, t.number);
    await expect(block).toBeVisible();
    await block.scrollIntoViewIfNeeded();
    const hour = (await page.locator(".rbc-timeslot-group").first().boundingBox())!.height; // one hour of grid
    const box = (await block.boundingBox())!;
    const [x, y] = [box.x + box.width / 2, box.y + 10];
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x, y + hour / 2, { steps: 10 });
    await page.mouse.move(x, y + hour, { steps: 10 });
    await page.mouse.up();

    await expect(toast(page)).toBeVisible();
    const moved = await get<Appt>(s.request, `/appointments/${a.id}`);
    expect(Date.parse(moved.starts_at) - Date.parse(a.starts_at)).toBe(60 * 60_000);
    expect(Date.parse(moved.ends_at) - Date.parse(a.ends_at)).toBe(60 * 60_000);
  } finally {
    await cancelAll(s.request, [a.id]);
  }
});
