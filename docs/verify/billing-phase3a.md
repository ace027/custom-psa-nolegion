# Manual check: Phase 3A proration and device counts

1. **Billing > Agreements**: create "Test users", per user, 10 users, $150.00, taxable, start on the 15th of this month (or any mid-month day).
2. **Billing > Runs**: start a run for that month. Open the client's draft invoice.
   - Expect two lines: the full-month agreement line and a `Proration: ... N of D days not covered` line with a negative amount.
   - For 15 Oct (31 days): lines 150,000 c and -67,742 c; with 8.25% tax, tax 6,786 c, total net of credit $822.58 + tax.
3. Create an agreement starting on the 1st: **no** proration line.
4. End an agreement on a mid-month day, rerun (cancel the draft run first): a credit for the days after the end date.
5. Void the draft invoice: both lines disappear from billing and a rerun produces them again.
6. **Revenue report**: after finalizing, the agreement column shows the net amount.
7. **Per-device agreement** with synced NinjaOne assets for the client: if the counts differ an amber note shows "NinjaOne reports N devices; this agreement says M". Nothing changes until you click **Update quantity**; then **history** shows the change with the reason "Updated from NinjaOne device count".
8. Retired assets and Hudu-only assets are not counted.
