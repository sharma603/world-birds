import frappe
from frappe.model.document import Document
from wob_delivery.permissions import assert_company


class WOBDeliveryZone(Document):
	def validate(self):
		self.validate_general_info()
		self.validate_settings()
		self.validate_coverage_areas()
		self.validate_company_and_orders()
		self.sync_assigned_drivers()

	def validate_general_info(self):
		if not (self.zone_name or "").strip():
			frappe.throw("Zone Name is required.")
		self.zone_name = self.zone_name.strip()

		# Normalize zone_code to uppercase trimmed
		self.zone_code = (self.zone_code or "").strip().upper()
		if not self.zone_code:
			frappe.throw("Zone Code is required.")

		# Zone Code must be unique per company
		existing = frappe.db.get_value(
			"WOB Delivery Zone",
			{"zone_code": self.zone_code, "company": self.company, "name": ["!=", self.name or ""]},
			"name",
		)
		if existing:
			frappe.throw(
				f"Zone Code '{self.zone_code}' is already used by Delivery Zone '{existing}' for {self.company}."
			)

		assert_company(self.company)
		self.zone_key = f"{self.company}::{self.zone_code}"

		# Currency defaults to company's default currency
		company_currency = frappe.db.get_value("Company", self.company, "default_currency")
		self.currency = company_currency or self.currency or "QAR"

	def validate_settings(self):
		if (self.delivery_charge or 0) < 0:
			frappe.throw("Default Delivery Charge cannot be negative.")

		if self.estimated_delivery_time and self.estimated_delivery_time < 0:
			frappe.throw("Estimated Delivery Time must be positive when provided.")

		if self.maximum_active_deliveries and self.maximum_active_deliveries < 0:
			frappe.throw("Maximum Active Deliveries must be positive when provided.")

	def validate_coverage_areas(self):
		seen_areas = set()
		for row in self.get("coverage_areas") or []:
			area_name = (row.area_name or "").strip()
			if not area_name:
				frappe.throw("Area Name is required for each coverage area row.")
			key = area_name.lower()
			if key in seen_areas:
				frappe.throw(f"Duplicate coverage area '{area_name}' found in this zone.")
			seen_areas.add(key)
			row.area_name = area_name
			if row.area_code:
				row.area_code = row.area_code.strip().upper()

	def validate_company_and_orders(self):
		old = self.get_doc_before_save()
		if old and old.company != self.company and frappe.db.exists(
			"WOB Driver Zone Assignment", {"delivery_zone": self.name}
		):
			frappe.throw("A zone with driver mappings cannot change company.")

		if not self.active and frappe.db.exists(
			"WOB Delivery Order",
			{
				"delivery_zone": self.name,
				"delivery_status": ["not in", ["Delivered", "Cancelled"]],
			},
		):
			frappe.throw("Complete or cancel active deliveries before disabling this zone.")

	def sync_assigned_drivers(self):
		if not self.name:
			return
		assignments = frappe.get_all(
			"WOB Driver Zone Assignment",
			filters={"delivery_zone": self.name, "company": self.company, "active": 1},
			fields=["driver", "driver_user", "assignment_type", "availability_status"],
			order_by="assignment_type, driver",
		)
		self.set("assigned_drivers", [])
		for a in assignments:
			driver_name = frappe.db.get_value("Driver", a.driver, "full_name") or a.driver
			self.append(
				"assigned_drivers",
				{
					"driver": a.driver,
					"driver_name": driver_name,
					"driver_user": a.driver_user,
					"assignment_type": a.assignment_type,
					"availability_status": a.availability_status,
				},
			)
