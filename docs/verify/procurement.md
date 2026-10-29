# Manual check: procurement and inventory (Phase 10)

Needs: an admin login, a read-only login, a client, a catalog product with a cost (taxable), and a billing run you can open.

## Vendors
- [ ] Procurement > Orders and vendors > Vendors > Add vendor (name, account number, email). It lists.
- [ ] Edit it, then Archive: it disappears. Tick "Show archived" and Restore it.
- [ ] With no vendors the tab says "No vendors yet."

## Purchase order
- [ ] Purchase orders > New purchase order: pick the vendor, add a line for the catalog product (quantity 2, serialised) and a free-text line (quantity 5, unit cost $10.00, not serialised, not billable).
- [ ] Create. You land on a Draft order with no number. Remove a line and confirm it goes.
- [ ] Order: the status becomes Ordered and a number appears.

## Receiving and serials
- [ ] Receive the serialised line: two serial inputs appear for quantity 2. Leaving one blank is refused on screen.
- [ ] Enter the same serial twice or a serial already in inventory: the server message shows in the dialog and nothing is received.
- [ ] Enter two different serials: the line shows 2 / 2 and the order is Partly received until the other line is received. Receive 3 of the 5 now, the rest later: Received at the end.

## Delivery and markup by hand
- [ ] Markup rules: leave the default at 0.00%. Add a Hardware category rule of 15.
- [ ] Inventory: Deliver a serialised unit costing $123.45 to the client, choosing "Create a new asset". The row is Delivered with markup 15.00%.
- [ ] The client page shows it in Hardware and inventory, and the new asset is in its Assets card.
- [ ] Run billing for that client. The invoice has a charge for $141.97 (cost $123.45 plus 15%), taxed like the product.
- [ ] Deliver the non-billable stock: no charge is created.
- [ ] Deliver part of a non-serialised row: the rest stays In stock.

## Undo and consume
- [ ] Deliver another unit, do not invoice it, then Undo delivery > Confirm undo: it is In stock again and its charge no longer appears on the next run.
- [ ] Undo the unit that is already on the invoice: the page shows "Already invoiced" and the unit stays Delivered. Fix with a credit memo.
- [ ] Consume an in-stock unit: confirm, then it shows "Used internally" and is never billed.

## Rules to confirm
- [ ] Billing happens on delivery, not on receipt.
- [ ] Markup order: set a rule on the product (20) and a markup on a PO line (5); the line value wins, then the product rule over the category rule.
- [ ] Changing a rule afterwards does not reprice an item already delivered.

## Permissions and states
- [ ] As the read-only user: Procurement is visible but there is no New purchase order, Order, Receive, Deliver, Consume, Undo, Edit or Add rule.
- [ ] A tech can receive and deliver, but Markup rules shows no edit controls.
- [ ] Empty lists say so (no purchase orders, no inventory).
