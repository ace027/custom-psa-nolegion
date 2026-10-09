# Statements and reminders: what to verify manually

Prep: dev stack + seed data. A client with a billing contact **that has an email address** and at least one
finalized invoice already past due (create it with a past invoice date and 0-day terms, or wait). Mail
setup is only needed for the last section. Sign in as `billing@example.com`.

## Preparing
- [ ] Billing > Reminders > *Prepare reminders now*: a notice appears for the client, naming the stage, recipients, and each invoice with days late
- [ ] Running it again creates nothing new (no duplicate, no repeat of a stage)
- [ ] The tab shows "N to review"; nothing was emailed
- [ ] A client with **no** contact email gets a notice marked *Blocked*, with Approve disabled
- [ ] Tick "Do not send payment reminders" on a client page: it gets no reminder

## Reviewing
- [ ] Edit the subject/text, *Save edits*: text persists after reload; Approve is disabled until you save
- [ ] Record a payment on one of the invoices: the notice shows "Balances have changed"; *Refresh* rewrites it; paying everything makes it expire
- [ ] *Dismiss* asks for a reason; the notice moves to Dismissed
- [ ] As `tech@example.com`: the page is read-only (no buttons)

## Statements
- [ ] Receivables > *Statement PDF* opens a PDF: open invoices with days late, payments since last statement, credit, aging summary
- [ ] Generate another after recording a payment: the payment appears under "payments since last statement"
- [ ] *Prepare statement email* lands in Reminders for approval
- [ ] *Prepare monthly statements* creates one per client with a balance; pressing it again creates none
- [ ] Settings > Payment reminders and statements: change a stage's days/text; an unknown `{placeholder}` is refused

## Sending (needs the mailbox configured and the worker running)
- [ ] *Approve & send*: the notice becomes Sent; within a minute the worker delivers it; the message has the invoice PDF attached
- [ ] Reply to it: a ticket is created/updated in the support queue
- [ ] With the mailbox NOT configured, Approve is refused with a clear message
- [ ] Audit log shows notice.create / notice.send / notice.dismiss / statement.create rows

## Invoice emails
- [ ] On a finalized invoice, *Prepare email to client*: lands in Billing > Client emails as an "Invoice" item with the right recipients and total; nothing is sent yet
- [ ] Preparing it again while it waits is refused; after it is sent you can prepare another
- [ ] Draft and voided invoices have no button / are refused
- [ ] Void the invoice while its email waits: Approve is refused; *Refresh* closes it as expired
- [ ] Settings: turn on "Prepare an invoice email when an invoice is finalized", finalize a run: one item per invoice, none sent
- [ ] Approve & send: the worker delivers it with `INV-....pdf` attached
