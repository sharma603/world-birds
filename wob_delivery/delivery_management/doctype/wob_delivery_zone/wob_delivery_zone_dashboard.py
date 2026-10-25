from frappe import _


def get_data():
	return {
		"fieldname": "delivery_zone",
		"transactions": [
			{"label": _("Deliveries"), "items": ["WOB Delivery Order"]},
			{"label": _("Drivers"), "items": ["WOB Driver Zone Assignment"]},
		],
	}
