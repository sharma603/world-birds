# Driver cash collection

On an assigned delivery that is Out for Delivery or Delivered, the driver opens Payment & Cash Collection, enters the cash actually received (blank means the displayed full balance), and selects Confirm Cash Received. Confirmation creates and submits an ERPNext Receive Payment Entry allocated to the linked Sales Invoice. Partial payments leave a remaining balance; full settlement lets ERPNext mark the invoice Paid. Mark Delivered alone never posts money.

Cash posts directly to the company's configured Cash mode-of-payment account, falling back to its default Cash account. This is not a separate driver-custody/handover ledger. Only Cash on Delivery in company currency is supported. A matching submitted Sales Invoice and valid Cash account are required. The phone cannot choose arbitrary accounts, invoices, companies, or customers.

The server locks delivery/invoice rows, verifies the active assigned driver, validates precision and current balance, and stores a unique collection request ID. Retrying the same confirmation returns the existing receipt. Payment and allocation share the request transaction with no internal commit. Canceled receipts are excluded from mobile totals; cancellation/reconciliation remain accounting actions in ERPNext.

Drivers receive no additional accounting roles. A private service context runs the standard ERPNext payment builder and submit for the verified invoice/account. Payment Entry stores the Delivery Order, Collected By user, and unique request ID. Driver session/SID are restored even on failure. Drivers can read their own completed deliveries to collect payment afterward. Delivered delivery orders themselves are immutable: form/API edits, reassignment, reopening, renaming, and fulfillment-link changes are blocked even for managers. Cash collection posts a separate Payment Entry without editing the delivered order.

Setup adds three Payment Entry custom fields through after_migrate. For existing installations, run `bench --site SITE execute wob_delivery.payments.setup_fields` or migrate. No real payment is posted by setup.

Rollback-only integration checks cover partial/full payments, retries, balanced ledger entries, and live mobile summaries. No real invoice payment is retained during verification.
