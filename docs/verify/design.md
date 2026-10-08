# Look and feel: what to verify manually

Run both themes for each item (use the Auto / Light / Dark button, and also try changing the operating
system's light/dark setting while on Auto).

## Themes
- [ ] First visit follows the OS setting; no white flash on reload in dark mode
- [ ] The theme button cycles Auto, Light, Dark and the choice survives a reload (and is per browser)
- [ ] Sign-in page, dashboard, tickets, a ticket, organizations, a client page, billing (every tab), quotes, warranty, integrations, settings, users, audit log: text is readable, nothing white-on-white or dark-on-dark, no unstyled boxes
- [ ] Badges (SLA, warranty, status) are readable and still carry text, not just colour
- [ ] Form fields, dropdowns, date pickers and checkboxes look native-dark in dark mode

## Staff layout
- [ ] Sidebar highlights the current page; the Billing sub-tabs still work
- [ ] On a phone-width window (about 390px) the sidebar is hidden behind **Menu**, and choosing a page closes it
- [ ] No horizontal scrolling of the page itself on a phone (wide tables scroll inside their card)

## Portal
- [ ] Sign in, then Tickets, Invoices and Devices tabs
- [ ] Devices: four summary tiles, the coverage bar, and the table; counts match the table
- [ ] On a phone the header wraps cleanly and the devices table scrolls sideways inside its card

## Not changed
- [ ] Invoice, statement and quote PDFs, and emails, are still light and identical to before
