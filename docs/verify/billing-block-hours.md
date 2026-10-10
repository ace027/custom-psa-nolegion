# Manual check: block-hour agreements

1. **Billing > Agreements > New agreement**: pick a client, name "Support block", type **Block hours**. Confirm the form shows **Monthly fee ($)** and **Included hours** and hides the quantity. Enter $1,000.00, 10 hours (try 7.5 too: it shows "7.5 h included"), start on the 1st of this month. Create. The row shows "Block hours (10 h included)".
2. Log 12.5 hours of covered work for that client this month (several tickets/entries).
3. Run billing for the month. The invoice has the **block line** ($1,000.00) and the time lines show 10 h covered and a **2.5 h overage** billed at the work type rate.
4. **Billing > Rates**: tick **Not covered by blocks** on one work type (for example Onsite). Log 1 h of it, rerun (after voiding the previous run). That hour bills at its own rate and does not use up the block.
5. Log an entry that straddles the month end (starts the last evening, ends after midnight). Check the minutes split between the two months and each part is covered by its own month's block.
6. Void the run and run again. The same block line and overage appear; nothing is billed twice.
7. Try to create a second block for the same client overlapping the first. It is refused and the API message shows inline under the form.
8. Edit the block's included hours on the Agreements row and Save; the new figure shows. Set 0 or blank: an inline error appears.
9. Create an ad-hoc invoice for the client with "include unbilled". Confirm it leaves the block-month covered-type time out and shows the warning "N time entries in block-agreement months left for the monthly billing run". Run the monthly billing: that time is drawn down against the block.
10. The seed data includes "Support block" ($1,000.00, 10 h) for Northwind Legal.
