# Confirmed driver bank collections

User selected recording company-confirmed transfers. Extend assigned-driver collection service, preserving invoice locks, partial allocation, balance checks, Delivered lock and retry IDs. Bank receipts require an enabled Bank mode mapped to an active leaf Bank account in company/invoice currency. Client cannot specify an arbitrary account. Require reference and nonfuture transfer date. This records manual confirmation, not automatic bank verification.

Mobile exposes authorized valid payment choices and a missing-configuration explanation. Freeze method/reference/date with each retry ID. Preserve Cash compatibility and separate cash/bank totals. Current Bank Transfer is incorrectly mapped to Cash - AT and no Bank account exists; require correct configuration.

Validate account/company/currency, required reference/date and retry identity with unit tests; typecheck/lint mobile; test accounting under rollback where eligible invoices exist. Retain no test financial entries.
