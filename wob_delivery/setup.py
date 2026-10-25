"""Idempotent metadata setup; never creates demo transactions or user grants."""
import frappe

ROLES = [
	"WOB Delivery Administrator",
	"WOB Delivery Manager",
	"WOB Delivery Dispatcher",
	"WOB Delivery Driver",
]


def setup_delivery_sidebar():
	if not frappe.db.exists("Sidebar", "Delivery Management"):
		from frappe.desk.doctype.sidebar.sidebar import mark_as_standard

		mark_as_standard("Delivery Management")

	doc = frappe.get_doc("Sidebar", "Delivery Management")
	doc.set("items", [])

	items = [
		{
			"type": "Link",
			"label": "Home",
			"link_type": "Workspace",
			"link_to": "Delivery Management",
			"icon": "house",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"open_in_new_tab": 0,
			"show_arrow": 0,
			"hidden": 0,
			"added": 0,
			"is_default_module": 0,
		},
		{
			"type": "Link",
			"label": "Delivery Dashboard",
			"link_type": "Page",
			"link_to": "wob-delivery-dashboard",
			"icon": "chart-column",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"open_in_new_tab": 0,
			"show_arrow": 0,
			"hidden": 0,
			"added": 0,
			"is_default_module": 0,
		},
		{
			"type": "Link",
			"label": "Delivery Orders",
			"link_type": "DocType",
			"link_to": "WOB Delivery Order",
			"icon": "truck",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"open_in_new_tab": 0,
			"show_arrow": 0,
			"hidden": 0,
			"added": 0,
			"is_default_module": 0,
		},
		{
			"type": "Link",
			"label": "Drivers",
			"link_type": "DocType",
			"link_to": "Driver",
			"icon": "user-round",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"open_in_new_tab": 0,
			"show_arrow": 0,
			"hidden": 0,
			"added": 0,
			"is_default_module": 0,
		},
		{
			"type": "Link",
			"label": "Driver Zone Assignments",
			"link_type": "DocType",
			"link_to": "WOB Driver Zone Assignment",
			"icon": "map-pin",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"open_in_new_tab": 0,
			"show_arrow": 0,
			"hidden": 0,
			"added": 0,
			"is_default_module": 0,
		},
		{
			"type": "Link",
			"label": "Delivery Zones",
			"link_type": "DocType",
			"link_to": "WOB Delivery Zone",
			"icon": "map",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"open_in_new_tab": 0,
			"show_arrow": 0,
			"hidden": 0,
			"added": 0,
			"is_default_module": 0,
		},
		{
			"type": "Link",
			"label": "Assignment History",
			"link_type": "DocType",
			"link_to": "WOB Delivery Assignment History",
			"icon": "clock",
			"child": 0,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"open_in_new_tab": 0,
			"show_arrow": 0,
			"hidden": 0,
			"added": 0,
			"is_default_module": 0,
		},
		{
			"type": "Section Break",
			"label": "Reports",
			"icon": "sheet",
			"child": 0,
			"indent": 1,
			"collapsible": 1,
			"keep_closed": 0,
			"open_in_new_tab": 0,
			"show_arrow": 0,
			"hidden": 0,
			"added": 0,
			"is_default_module": 0,
		},
		{
			"type": "Link",
			"label": "Delivery Register",
			"link_type": "Report",
			"link_to": "WOB Delivery Register",
			"icon": "table",
			"child": 1,
			"indent": 0,
			"collapsible": 1,
			"keep_closed": 0,
			"open_in_new_tab": 0,
			"show_arrow": 0,
			"hidden": 0,
			"added": 0,
			"is_default_module": 0,
		},
	]

	for item in items:
		doc.append("items", item)

	doc.standard = 1
	doc.save()


def setup_payment_accounts():
	"""Ensure companies have receiving accounts mapped for enabled payment modes."""
	companies = frappe.get_all("Company", fields=["name", "abbr", "default_currency", "default_bank_account", "default_cash_account"])
	for comp in companies:
		currency = comp.default_currency or "QAR"
		parent_bank = frappe.db.get_value(
			"Account",
			{"company": comp.name, "account_name": "Bank Accounts", "is_group": 1},
			"name",
		)
		if parent_bank:
			bank_ledger = frappe.db.get_value(
				"Account",
				{"company": comp.name, "account_type": "Bank", "is_group": 0, "disabled": 0},
				"name",
			)
			if not bank_ledger:
				account_name = "CBQ" if comp.name == "Alam Trading" else "Bank Account"
				bank_doc = frappe.get_doc({
					"doctype": "Account",
					"account_name": account_name,
					"company": comp.name,
					"parent_account": parent_bank,
					"account_type": "Bank",
					"account_currency": currency,
					"is_group": 0,
				})
				bank_doc.insert(ignore_permissions=True)
				bank_ledger = bank_doc.name

			if not comp.default_bank_account:
				frappe.db.set_value("Company", comp.name, "default_bank_account", bank_ledger)

			bank_modes = frappe.get_all("Mode of Payment", filters={"type": "Bank", "enabled": 1}, fields=["name"])
			for bm in bank_modes:
				mop_doc = frappe.get_doc("Mode of Payment", bm.name)
				mapping = next((row for row in mop_doc.accounts if row.company == comp.name), None)
				needs_update = False
				if mapping and mapping.default_account:
					acc_data = frappe.db.get_value("Account", mapping.default_account, ["company", "account_type", "disabled"], as_dict=True)
					if not acc_data or acc_data.company != comp.name or acc_data.account_type != "Bank" or acc_data.disabled:
						needs_update = True
				else:
					needs_update = True

				if needs_update:
					if mapping:
						mapping.default_account = bank_ledger
					else:
						mop_doc.append("accounts", {"company": comp.name, "default_account": bank_ledger})
					mop_doc.save(ignore_permissions=True)

		if frappe.db.exists("Mode of Payment", "Cash"):
			cash_mop = frappe.get_doc("Mode of Payment", "Cash")
			cash_mapping = next((row for row in cash_mop.accounts if row.company == comp.name), None)
			cash_acc = comp.default_cash_account or frappe.db.get_value(
				"Account", {"company": comp.name, "account_type": "Cash", "is_group": 0, "disabled": 0}, "name"
			)
			if cash_acc and (not cash_mapping or not cash_mapping.default_account):
				if cash_mapping:
					cash_mapping.default_account = cash_acc
				else:
					cash_mop.append("accounts", {"company": comp.name, "default_account": cash_acc})
				cash_mop.save(ignore_permissions=True)


def after_migrate():
	from wob_delivery.payments import setup_fields as setup_payment_fields
	setup_payment_fields()
	from wob_delivery.sales_order_status import setup_fields
	setup_fields()
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
	setup_delivery_sidebar()
	setup_payment_accounts()
	frappe.db.set_single_value("Print Settings", "allow_print_for_cancelled", 1)
	frappe.reload_doc("delivery_management", "print_format", "wob_delivery_slip")
	frappe.reload_doc("delivery_management", "print_format", "wob_sales_order_delivery_slip")
	frappe.reload_doc("delivery_management", "print_format", "alam_trading_sales_invoice")
	frappe.reload_doc("delivery_management", "print_format", "alam_trading_delivery_note")
	frappe.make_property_setter({
		"doctype": "Sales Invoice",
		"property": "default_print_format",
		"value": "Alam Trading Sales Invoice",
		"property_type": "Data",
	})
	frappe.make_property_setter({
		"doctype": "Delivery Note",
		"property": "default_print_format",
		"value": "Alam Trading Delivery Note",
		"property_type": "Data",
	})
	if frappe.db.exists("Print Format", "Delivery Note"):
		frappe.db.set_value("Print Format", "Delivery Note", "disabled", 1)
	frappe.clear_cache()


after_install = after_migrate


def setup_dashboard_indexes():
 """Explicitly callable, idempotent indexes; no transaction data is created."""
 indexes = {
  'WOB Delivery Order': [
   ['company', 'delivery_status', 'scheduled_delivery_date'],
   ['assigned_driver', 'delivery_status', 'scheduled_delivery_date'],
   ['company', 'delivery_zone', 'scheduled_delivery_date'],
   ['delivery_status', 'completed_at'],
  ],
  'WOB Delivery Assignment History': [['delivery_order', 'changed_at']],
  'Payment Entry': [['custom_wob_delivery_order', 'docstatus', 'posting_date']],
 }
 for doctype, groups in indexes.items():
  for fields in groups:
   frappe.db.add_index(doctype, fields)
