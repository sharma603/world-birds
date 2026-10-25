import frappe
from frappe.model.document import Document
from wob_delivery.permissions import assert_company

class WOBDriverZoneAssignment(Document):
 def validate(self):
  assert_company(self.company)
  zone=frappe.get_doc('WOB Delivery Zone',self.delivery_zone)
  if zone.company!=self.company: frappe.throw('Zone and mapping must belong to the same company.')
  driver=frappe.get_doc('Driver',self.driver)
  if self.active and (not zone.active or driver.status!='Active'): frappe.throw('Only active zones and drivers can receive active mappings.')
  if not driver.user or not frappe.db.get_value('User',driver.user,'enabled') or frappe.db.get_value('User',driver.user,'user_type')!='System User':
   frappe.throw('Link the driver to an enabled ERPNext System User first.')
  if not set(frappe.get_roles(driver.user)).intersection({'WOB Delivery Driver','WOB Delivery Manager','WOB Delivery Administrator','System Manager'}):
   frappe.throw('The driver user needs an authorized WOB Delivery role.')
  self.driver_user=driver.user
  self.mapping_key=f'{self.company}::{self.delivery_zone}::{self.driver}'
  if (self.maximum_active_deliveries or 0)<0: frappe.throw('Maximum active deliveries cannot be negative.')
  old=self.get_doc_before_save()
  if old and any(old.get(k)!=self.get(k) for k in ['driver','company','delivery_zone']):
   frappe.throw('Driver, company and zone are immutable. Deactivate the old mapping and create a new one.')
 def on_update(self):
  zone=frappe.get_doc('WOB Delivery Zone',self.delivery_zone)
  zone.save(ignore_permissions=True)
 def on_trash(self):
  assert_company(self.company)
  if self.delivery_zone and frappe.db.exists('WOB Delivery Zone', self.delivery_zone):
   try:
    zone = frappe.get_doc('WOB Delivery Zone', self.delivery_zone)
    zone.save(ignore_permissions=True)
   except Exception:
    pass
