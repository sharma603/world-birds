### WOB Delivery

Delivery Management for Worlds of Birds

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app wob_delivery
```

### Sales Order fulfillment automation

On the first save of a new WOB Delivery Order linked only to a submitted Sales Order,
the app creates and submits a Delivery Note, then creates and submits a Sales Invoice
from that Delivery Note. The generated references are attached to the delivery task.
The Delivery Note posts stock; the invoice uses `update_stock = 0` to avoid deducting stock twice.
ERPNext validates warehouses, stock, serial/batch requirements, fiscal years, accounts,
prices and user permissions. The creator must have Create and Submit permission for both documents.
All documents share the save transaction; any failure prevents partial fulfillment.

Orders with an existing non-cancelled draft or submitted Delivery Note or Sales Invoice
are blocked from automatic creation to prevent duplicates. Review and link existing
submitted documents through the established delivery workflow instead. Deliveries
already linked to documents are not posted again, and existing delivery tasks are
not processed retroactively. Cancelling a delivery task does not cancel its stock
or accounting documents; those require ERPNext's normal cancellation/reversal process.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/wob_delivery
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
