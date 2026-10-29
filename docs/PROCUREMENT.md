# Procurement: vendors, purchase orders, inventory and markup

The Procurement area (`/procurement`) is for staff with `procurement:read`. It covers who you buy from, what you ordered, what is on the shelf, and what you hand to a client (and bill them for).

All money is in dollars on screen and whole cents in the API. Markup is entered as a percent (15 or 8.25) and stored as basis points (1500, 825).

## Vendors
A vendor has a name, account number, email, phone, website and notes. Add and edit them on Procurement > Vendors. **Archive** hides a vendor from the new-order list but keeps its history; tick "Show archived" and use **Restore** to bring one back.

## Purchase order lifecycle
| Status | Meaning | What you can do |
|---|---|---|
| Draft | Being written, no number yet | Edit vendor, client and lines; Remove a line; **Order**; Cancel |
| Ordered | Placed with the vendor | Receive; Cancel (only while nothing is received) |
| Partly received | Some units received | Receive the rest |
| Received | Every line fully received | Read only |
| Cancelled | Dropped | Read only |

A line is either a catalog product (description, unit cost and taxable default from the product) or free text (description and unit cost required). Each line also has: quantity, **serialised** (each unit has its own serial number), **billable** (becomes a client charge on delivery) and an optional markup percent. A PO may name a client; its stock is then reserved for that client.

## Receiving and serial numbers
Press **Receive** on a line, enter the quantity that arrived (up to what is still outstanding) and, for a serialised line, one serial number per unit. The server rejects a duplicate serial (in the same request or already in inventory) and the message appears in the dialog. Partial receipts are fine; the PO moves to Partly received and then Received. Receiving creates inventory items: one row per unit for serialised lines, one row for the whole quantity otherwise.

## Inventory statuses
- **In stock**: on the shelf (possibly reserved for the client named on the PO).
- **Delivered**: handed to a client. A billable item has a product charge.
- **Used internally**: consumed by you; never billed.

Filter by status, client or search text (description or serial).

## Delivery and assets
**Deliver** asks for the client, and a quantity for non-serialised stock (delivering part of a row splits it; the rest stays in stock). Optionally:
- link an **existing asset** of that client, or
- **create an asset** (kind `other`, named after the item, with the serial).
Only a serialised item or a single unit can be linked to an asset. A client's delivered and reserved items show on the client page in the Hardware and inventory card.

## Markup resolution
The markup for a delivered item is the first that applies:
1. the markup set on the PO line;
2. the rule for that product;
3. the rule for the product's category (hardware, software, license, other);
4. the default markup (Procurement > Markup rules; the same value is in Settings). It starts at 0%.

The price is cost plus markup, with the markup rounded half up to a whole cent.

**Worked example:** a unit costs $123.45 and the markup is 15%. 12,345 cents x 15% = 1,851.75, rounded to 1,852 cents. Price = 12,345 + 1,852 = 14,197 cents = **$141.97**.

The percent used is saved on the item at delivery, so changing or deleting a rule later never reprices a delivered item.

## Undo rules
- **Undo delivery** returns the item to stock and voids its charge, but only while the charge is not on an invoice. Once invoiced the server answers "Already invoiced: issue a credit memo instead" and nothing changes; use a credit memo (see BILLING.md).
- An asset created by a delivery is kept after an undo.
- Undoing the delivery of a row that was split does not merge it back; it returns to stock as its own row.
- **Consume** marks in-stock items as used internally. It has its own confirmation.

## Permissions
| Action | Permission |
|---|---|
| View vendors, orders, inventory, markup rules, client card | `procurement:read` |
| Edit vendors and orders, receive, deliver, undo, consume | `procurement:write` (admin, tech, billing) |
| Add, change or delete markup rules; change the default markup | `billing:write` (the default markup is a setting, so saving it also needs the settings permission, `config:manage`) |

Users without write permission (read-only) see the pages with no action buttons. Techs can run the whole workflow but cannot change markup rules (no `billing:write`).
