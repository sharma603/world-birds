# WOB Delivery Management — Phase 1 implementation

The supplied Phase 1 document is the implementation brief. Extend the installed `wob_delivery` app, preserving existing branding and ERPNext core.

## Existing installation
- Frappe 16, ERPNext 16, installed WOB Delivery scaffold; no delivery DocTypes yet.
- Alam Trading, World of Birds, Birds Center exist.
- Standard Driver includes status, User, contact and licence data.

## Structure
- `wob_delivery/delivery_management/doctype/`: zone, zone driver child, driver zone assignment, delivery order, immutable assignment history.
- `wob_delivery/domain.py`: pure status and collection rules.
- `wob_delivery/permissions.py`: shared company, role and assigned-driver policy.
- `wob_delivery/services.py`: authoritative document references, workload, locking and history.
- `wob_delivery/api.py`: permission-filtered dashboard, eligible documents and driver recommendations.
- `delivery_management/page/wob_delivery_dashboard/`: native Desk page, filters, counts, breakdowns and order list.
- `delivery_management/report/wob_delivery_register/`: permission-filtered delivery register.
- `delivery_management/workspace/delivery_management/`: navigation.
- `wob_delivery/setup.py`, `tests/`, `docs/`: repeatable setup, tests and operation guide.

## Execution sequence
1. Write and run failing domain tests for transitions, collection and access decisions.
2. Add schema, shared rules, authoritative reference checks, duplicate prevention, concurrent assignment protection and append-only audit.
3. Add permission-filtered APIs, native Desk UI/report and workspace.
4. Test pure rules and installed-site integration (assignment, reassignment, company/driver isolation, duplicates, inactive users/drivers, amounts).
5. Apply schema without modifying existing business documents; validate browser and document setup/limitations.

## Decisions
- Manual assignment only; no mobile app, automatic dispatch, payment posting, stock posting or cash handovers.
- Company restrictions are mandatory for managers/dispatchers; group administrators retain group access.
- Drivers have read access only to their own current active tasks; driver status mutation remains a future authenticated API phase.
- Invoice outstanding is authoritative for amount-to-collect; otherwise use submitted Sales Order total less advances. Prepaid/Bank Transfer tasks collect zero only when no balance remains; otherwise show a clear validation message.
- Source documents must be submitted and match company/customer; Delivery Note tasks need an invoice/order for collection.
- Reassignment requires a reason and updates history atomically. Final status changes require a manager and reason.
- No sample sales, drivers, companies or payments are created on this site.
