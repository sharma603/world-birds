# Alam Trading Live Delivery Control Center

Implement the user's supplied specification in existing Frappe Desk. Preserve workflows, immutable delivered orders, mobile alerts/payments, and company/driver permissions. No new frontend framework. Use scoped navy CSS, an authoritative consolidated API, safe contextual actions, and per-user after-commit events.

## Shared API contract
`wob_delivery.api.get_dashboard` extends existing arguments with `customer_search`, `order_search`, `page` (1), `page_size` (25), `sort_by` (`scheduled_delivery_date`), `sort_order` (`asc`), `completed_today` (0), `issues_only` (0). Response keeps `counts`, `delivered_today`, `by_zone`, `by_driver`, `by_company`, `orders`, mobile cash fields; adds `pagination:{page,page_size,total,total_pages}`, `server_time`, `timezone`, `can_manage`.

Analytics rows keep old group keys (`delivery_zone`, `assigned_driver`, `company`) and add `label`, `count`, `counts` status map, `active_count`, `delivered_today`. Driver rows also have `driver_name`. Orders include old fields plus `payment_type`, `modified`, and `driver_name` (bulk lookup). All counts/analytics/tasks share filters; today completion intersects rather than overrides those filters. The issue KPI scopes Failed/Rescheduled via boolean, without inventing a business status.

`wob_delivery.dashboard.get_task_details(name)` returns `{order,timeline}` checked through delivery read permission. Timeline projects actual assignment-history fields only. `wob_delivery.dashboard.perform_action(name,action,driver=None,reason=None)` accepts `ready`, `assign`, `dispatch`, `delivered`, `failed`, reusing existing save validations and company/record checks. Delivered rows have no mutations.

`wob_delivery_changed` is published after commit to authorized user rooms, not the entire site. Payload contains delivery ID, action, company, revision/event ID only, no customer/financial values. Page subscribes once while visible and cleans up on hide/reinit. Actual socket state controls connection badge; disconnected reconciliation is 30 seconds, connected reconciliation 60 seconds, with hidden-page inactivity and site-date rollover checks.

## Work ownership
- Backend agent: dashboard.py; get_dashboard wrapper; optional bulk recommendation optimization; backend query/action tests; idempotent indexes in setup.py.
- Frontend agent: dashboard page JS and CSS; frontend synchronization tests. Preserve Sales Document picker fixes.
- Main agent: scoped event publisher/controller/mobile/payment integration; event tests; browser and cross-session validation; integration corrections.

## Verification
- Unit tests for filters, counts, paging, sort allowlists, permissions, transitions, scoped events, event batching, stale responses and listener cleanup.
- Actual API checks against local DB with rollback fixtures, including >1000 tasks and permission-scoped users.
- Actual authenticated sockets: two clients; committed test event receipt; rollback silence; no unauthorized notifications.
- Browser desktop/mobile layout, filter/table/action errors and empty states, actual Live badge.
- Preserve all existing Python and JS checks; record limits instead of claiming unexecuted scenarios.
