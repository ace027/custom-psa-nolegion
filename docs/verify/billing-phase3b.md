# Manual check: Phase 3B credit memos and refunds

1. Finalize an invoice with a taxable line of $141.97 at 8.25% (total $153.68).
2. **Billing > Credit memos > Issue**: that client, reason "Billed in error", one taxable line $141.97, pick the invoice under "Corrects invoice". Expect a memo `CM-<year>-0001` for $153.68.
3. Open its **details**, choose the invoice, Apply $153.68. The invoice now shows balance $0.00 and "Credited $153.68"; its total is unchanged.
4. Issue a second memo for $40.00 with no application: receivables shows $40.00 **credit** for the client; apply it to another open invoice later.
5. Try to apply more than the memo's value or more than the invoice balance: refused with a clear message.
6. **Undo** an application (reason required): the invoice owes again. **Void** the memo (reason required): all its applications are undone and it is struck through.
7. Try to void an invoice that has memo value applied: refused until you undo it.
8. **Payments**: record a $100.00 payment with $40.00 applied. In its details record a $60.00 refund (check #, reason). Expect unapplied $0; a $60.01 refund is refused. Money applied to an invoice cannot be refunded until you undo that application.
9. Void the refund (reason): the $60.00 is available again. Try voiding the payment while a refund is live: refused.
10. **Audit log** shows `credit_memo.create/apply/void` and `payment.refund/refund_void`.
