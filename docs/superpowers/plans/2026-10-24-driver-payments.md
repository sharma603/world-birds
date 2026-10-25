# Driver Payments Implementation Plan

**Goal:** Driver-confirmed cash receipts create submitted Payment Entries and reduce the linked invoice's outstanding balance.

**Architecture:** A narrow authenticated endpoint verifies the active assigned driver, locks delivery/invoice rows, validates amount/current balance, and uses the company's configured Cash account. The ERPNext payment builder/submit workflow runs in a private, tightly scoped service context; no accounting roles are granted to drivers. Submitted payments store delivery, collector, and unique request identifiers. Details/list summaries derive from submitted receipts and live invoice balances.

**Tech Stack:** Frappe/ERPNext Payment Entry; Expo/React Native; TanStack Query.

**Scope:** Cash on Delivery in company currency, full or partial payments. Payment is explicit; Delivered alone never posts money. Current login can view its own delivered tasks for collection. Invoice status and ledgers use standard ERPNext posting; canceled payments are excluded from totals. Existing company Cash accounts are used, with no separate driver custody/handover ledger.

- [x] Add receipt metadata and payment validation/idempotency tests; confirm failures.
- [x] Implement locked receipt posting and payment summaries with explicit collector audit.
- [x] Expose own delivered tasks and add receipt summaries to mobile details/list.
- [x] Add amount confirmation, retry token, successful-state refresh, and invoice balance to mobile UI.
- [x] Apply idempotent metadata; verify partial/full posting, retry, scope, and rollback against local ERPNext.
- [x] Run Python/mobile tests, TypeScript, lint; document use and limitations.

**Review focus:** Concurrent invoice changes; duplicate confirmations; other drivers' tasks; canceled receipts; partial payments; no cash account; invoice/customer/company/currency mismatches; no real accounting test commits.
