import frappe
from frappe.model.document import Document

class WOBDeliveryAssignmentHistory(Document):
 def before_insert(self):
  if not getattr(frappe.local,'wob_audit_write',False): frappe.throw('Assignment history is created only by delivery changes.',frappe.PermissionError)
 def validate(self):
  if not self.is_new(): frappe.throw('Assignment history cannot be changed.',frappe.PermissionError)
 def on_trash(self):
  frappe.throw('Assignment history cannot be deleted.',frappe.PermissionError)
