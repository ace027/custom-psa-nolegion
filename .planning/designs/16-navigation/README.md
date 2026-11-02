# Phase 16: navigation mockups

Three ways to cut down the left sidebar. Open the files directly in a browser (no build, no network):

- `mockup-a.html`: grouped, collapsible sidebar
- `mockup-b.html`: top bar of areas, with a left sub-nav for the current area
- `mockup-c.html`: icon rail of pinned pages, plus a command palette (Ctrl/Cmd+K)

Each one shows the ticket queue with sample rows, the running-timer bar, the on-call widget and the account controls. The dark strip at the top is not part of the app. Use it to switch **View as: Tech / Billing / Read-only / Admin** and to turn on dark mode. Click any nav item: the ticket queue is the only page drawn in full, and every other page shows where it now lives and its route today. Colours, font and dark theme come from `frontend/src/index.css`. Section open/closed state and pins are kept in your browser only.

## What the sidebar has today

`frontend/src/App.tsx` (`Layout`, lines 112-143) shows a flat list of up to 26 links. Only Reports has a heading. Access per link follows `can()` and the role matrix in `backend/app/permissions.py`:

| Seen by | Links |
|---|---|
| Every staff role | Dashboard, Tickets, Dispatch, On-call, Projects, Organizations, Sales, Billing, Procurement, Knowledge base, Quotes, Users |
| Admin, tech (`time:write`) | My timesheet, My expenses |
| Admin, billing (`report:read`) | SLA report, Utilisation report, Aging report, Profitability report, Report schedules, Warranty |
| Admin only | Integrations, API keys, Webhooks, Automation, Settings, Audit log |

So a tech sees 14 links, read-only sees 12, billing sees 18 and admin sees 26. Several pages also have their own tab bar. Billing has 11 tabs (Monthly runs, Invoices, Receivables, Client emails, Payments, Credit memos, Late fees, Agreements, Products, Rates, and Reports for admin and billing). Sales has 4 (Pipeline, Leads, Forecast, Renewals). Procurement has 3 (Orders and vendors, Inventory, Markup rules). Quotes links to its Rate card. Profile is the name link in the sidebar footer. Search is the box at the top.

All three mockups keep these permission rules. A role never sees a link it cannot open, and an empty group never shows its heading.

---

## Mockup A: grouped sidebar

**Idea.** Keep the left sidebar but sort it into five collapsible sections: Service desk, Scheduling, Clients & sales, Finance and Reports. Dashboard stays at the top. Each role starts with only its daily sections open: a tech gets Service desk and Scheduling, billing gets Finance and Reports, admin gets Service desk, Scheduling and Finance. Opening a page opens its section, and the sidebar remembers what you open or close. The six admin pages move behind one **Admin** entry. It opens an Admin overview page with its own sub-navigation (Overview, Users, Settings, Integrations, Automation, Webhooks, API keys, Audit log). Non-admins see a plain **Users** link in that spot. The tab bars inside Billing, Sales and Procurement stay as they are.

**Who it suits.** Everyone, and techs in particular: the sidebar looks the same as today, just shorter. With default settings a tech sees 9 links and 2 collapsed headings instead of 14 links. Admin sees 11 links and 2 collapsed headings instead of 26 links.

**Pros.** It is the smallest change, mostly inside `Layout`. People keep their current habits. The groups make clear what belongs together. Admin clutter disappears for good. The current mobile "Menu" drawer still works.
**Cons.** It is still a long list once every section is open. Billing's 11 tabs are still a crowded tab bar. Section headings add one click the first time you open a group.

| Current item | New location |
|---|---|
| Dashboard | Sidebar, top (no section) |
| Tickets, Projects, Knowledge base | Service desk |
| Dispatch, On-call, My timesheet, My expenses | Scheduling |
| Organizations, Sales, Quotes | Clients & sales |
| Billing, Procurement | Finance (their tabs unchanged) |
| SLA, Utilisation, Aging, Profitability report, Warranty, Report schedules | Reports |
| Users | Admin overview sub-nav (admin); plain "Users" link at the bottom (others) |
| Settings, Integrations, Automation, Webhooks, API keys, Audit log | Admin > its sub-nav, plus a card each on the Admin overview |
| Search | Sidebar, top |
| Profile, Sign out, theme, On-call widget | Sidebar footer (unchanged) |

**Accessibility.** Each section heading is a `<button>` with `aria-expanded` and `aria-controls`, so it works with Enter and Space and screen readers announce "collapsed" or "expanded". A collapsed section also shows how many pages it holds. The current link has `aria-current="page"`. Tab order: skip link, then search, Dashboard, each section heading followed by its links (only when open), Admin, on-call, profile, sign out, theme, then the page. The Admin sub-nav is a second `<nav aria-label="Admin">`. After a page change, focus moves to the page heading and the document title updates. The red badge on Billing has a text equivalent ("3 overdue invoices").
**Responsive.** At 768 px and up the sidebar is fixed at 15 rem. Below that it becomes today's top bar with a Menu button (`aria-expanded`) that opens the same grouped list, and choosing a link closes it. The Admin sub-nav stacks above the admin page on phones.

---

## Mockup B: top bar and area sub-nav

**Idea.** A top bar with six areas (Home, Service desk, Scheduling, Clients & sales, Finance, Reports), search, the on-call chip, an Admin gear and an account menu. A left sub-nav lists only the current area's pages. Pages that have tabs today become headed groups in the sub-nav. Under Finance, for example, there is a Billing heading over its 11 tabs and a Procurement heading over its 3, so those in-page tab bars go away. Home (Dashboard) has no sub-nav and uses the full width.

**Who it suits.** The owner and the billing role, who move between many sub-pages inside Finance and Reports. It also suits the service manager, who spends long stretches inside one area.

**Pros.** It gives the clearest "where am I" of the three: the area is highlighted at the top and the page on the left. It removes the long Billing tab bar. It scales well as pages are added to an area. Areas a role cannot use simply disappear: tech and read-only get 5 areas, with no Reports.
**Cons.** It is the biggest change to how the app feels. Moving between areas takes two clicks (area, then page), for example from Tickets to Billing > Invoices. The top bar runs out of room at tablet widths. Some pages (BillingLayout, Sales, PurchaseOrders) would need their tab bars removed.

| Current item | New location |
|---|---|
| Dashboard | Top bar: Home (also the logo) |
| Tickets, Projects, Knowledge base | Service desk sub-nav (plus a "New ticket" button) |
| Dispatch, On-call, My timesheet, My expenses | Scheduling sub-nav |
| Organizations | Clients & sales sub-nav |
| Sales (Pipeline, Leads, Forecast, Renewals tabs) | Clients & sales > "Sales" group |
| Quotes (and Rate card) | Clients & sales > "Quotes" group: All quotes, Rate card |
| Billing (11 tabs, Billing reports for admin and billing) | Finance > "Billing" group |
| Procurement (3 tabs) | Finance > "Procurement" group |
| SLA, Utilisation, Aging, Profitability report, Warranty, Report schedules | Reports sub-nav (admin and billing only) |
| Users | Gear icon > Admin sub-nav (admin); people icon labelled "Team" (others) |
| Settings, Integrations, Automation, Webhooks, API keys, Audit log | Gear icon > Admin sub-nav |
| Search | Top bar |
| On-call widget | Top bar chip ("On call: Alex Chen") |
| Profile, Sign out, theme | Account menu (initials button) |

**Accessibility.** There are two landmarks: `<nav aria-label="Areas">` and a sub-nav labelled "<Area> pages". The current area has `aria-current="true"` and the current page has `aria-current="page"`. Group headings in the sub-nav label their lists (`aria-labelledby`). The account menu and the mobile area menu are disclosure buttons with `aria-expanded`, and Esc closes them and returns focus to the button. Tab order: skip link, logo, areas, search, Admin, account, sub-nav, page. Focus moves to the page heading after navigation.
**Responsive.** Under 1100 px the on-call chip is hidden. Under 900 px the areas fold into a menu button on the left, and the sub-nav becomes a scrollable row of links above the page. On phones that row is long for Finance (14 links). It would want a "More" menu or a select in the real build.

---

## Mockup C: icon rail and command palette

**Idea.** An 80 px rail holding the pages each person pins, with "Go to" at the top and "All pages" below. The default pins depend on the role: a tech gets Tickets, Dispatch, Timesheet, Knowledge base and Organizations. Anyone can pin or unpin up to 8 pages with the star on each page header, in All pages, or with Alt+P in the palette. **Ctrl/Cmd+K** (or `/`, or the search box in the header) opens a palette. It finds every page the role can open, including Billing and Sales tabs such as "invoices" or "renewals". It also matches synonyms ("clients", "overdue", "queues"), opens a ticket from its number ("10477"), and runs quick actions (New ticket, Start a timer, Book an appointment, New quote, New KB article, Record a payment). With nothing typed, it shows Pinned, Recent and Actions. "All pages" opens a panel listing everything, grouped the same way as A, with a star next to each page.

**Who it suits.** Keyboard-heavy techs and the owner, once they know it. It also suits people who use only 4 to 6 pages, because the rail holds exactly those.

**Pros.** It needs the least screen space, which leaves room for the dispatch board and wide tables. Each person tunes it to their job. It is the fastest way to reach deep pages ("credit memos" in three keystrokes). Ticket-number jump is a big win for techs.
**Cons.** Pages you have not pinned are hard to discover: occasional users must know the palette or All pages exists. It is a new pattern for non-technical staff. It needs the most new code (palette, pin storage, ideally saved per user on the server). Icons alone are ambiguous at this page count, which is why the rail shows short labels.

| Current item | New location |
|---|---|
| Dashboard | Palette; All pages > Home; logo; pinnable (pinned by default for admin) |
| Tickets | Pinned by default (tech, read-only, admin); palette; ticket-number jump |
| Projects, Knowledge base | All pages > Service desk; palette; pinnable (KB pinned for tech and read-only) |
| Dispatch, On-call, My timesheet, My expenses | All pages > Scheduling; palette; Dispatch and Timesheet pinned for tech |
| Organizations | All pages > Clients & sales; pinned for tech, billing and read-only |
| Sales (and its 4 tabs) | All pages > Clients & sales, each tab listed; palette; Pipeline pinned for admin |
| Quotes, Rate card | All pages > Clients & sales; palette |
| Billing (and its 11 tabs) | All pages > Finance, each tab listed and pinnable; billing role pins Invoices, Receivables, Monthly runs |
| Procurement (and its 3 tabs) | All pages > Finance; palette |
| SLA, Utilisation, Aging, Profitability report, Warranty, Report schedules | All pages > Reports; palette; SLA pinned for admin, Aging for billing |
| Users | All pages > Admin (admin) or Team (others); palette |
| Settings, Integrations, Automation, Webhooks, API keys, Audit log | All pages > Admin; palette; Settings pinned for admin |
| Search | Header "Go to" box and the palette (search across records would be added there too) |
| On-call widget | Header chip |
| Profile, theme | Bottom of the rail |
| Sign out | Profile page (shortcut: not drawn in the mockup) |

**Accessibility.** The rail is `<nav aria-label="Main">`, and pinned pages are a labelled list. Each rail item shows a visible short label, and its accessible name contains that label (WCAG 2.5.3). The palette is a modal `role="dialog"` holding a `role="combobox"` input and a `role="listbox"`. Arrow keys move through results (`aria-activedescendant`), Enter opens, Esc closes and returns focus to whatever opened it, and Tab stays in the dialog. The key hints are linked to the input with `aria-describedby`. Pinning is announced through a `role="status"` live region. Stars in All pages are toggle buttons (`aria-pressed`, "Pin Billing Invoices"). The "Go to" buttons advertise `aria-keyshortcuts`. The All pages panel closes with Esc and returns focus to its button. Tab order: skip link, Go to, pinned pages, All pages, profile, theme, header (pin, Go to box), page.
**Responsive.** Under 768 px the rail becomes a bottom tab bar: Go to, the first 4 pins, and All pages, which opens as a sheet above the bar. The header keeps the Go to box. On phones the palette is the main way to move around, so its touch targets are full-width rows.

---

## Recommendation

**Build A, and add the command palette from C on top of it.** A fixes the actual complaint ("too many options") with the least risk. The sidebar techs live in keeps its shape. Admin-only pages move out of everyone's way. The change stays mostly inside `Layout` in `App.tsx`, and the existing mobile Menu still works. The palette (Ctrl/Cmd+K, page and tab search, ticket-number jump, quick actions) then gives the owner and power users the speed of C without making anyone depend on it. Pins can come later if people ask for them. I would not pick B now. It changes the most and makes jumps between areas take two clicks, which techs do constantly (Tickets to Dispatch to Timesheet). Its best idea, turning Billing's 11 tabs into a side list, can be applied inside the Billing page on its own.

## Open questions for the owner

1. Which direction: A, B, C, or A with the palette (recommended)?
2. Should techs and read-only users see Finance (Billing, Procurement) at all? Today they do, because `billing:read` and `procurement:read` are granted to every role.
3. The service manager has no role of its own, so today they must be admin to see reports. Do you want a "manager" role (dispatch, reports, SLA, time-off approval, without billing finalisation or admin), or is admin fine?
4. Should Users stay visible to every role as a staff directory, or move under Admin only?
5. Settings is one long page with about 22 cards. Should it be split into sub-pages under Admin (Mail and calendar, Tickets, Billing, Portal, Sales, Scheduling)? That would be a separate task.
6. Labels: keep "Organizations" and "Sales", or use "Clients" and "CRM"? The mockups keep today's names.
7. Should section open/closed state (A) and pins (C) be saved per browser, or per user on the server so they follow people between machines?
8. Should Billing reports stay under Billing, or also appear in Reports?
