import frappe
from frappe.model.document import Document
from wob_delivery.services import validate_order, record_history, assert_delivery_editable
from wob_delivery.permissions import assert_company
from wob_delivery.sales_order_status import sync_sales_order_status
from wob_delivery.mobile import publish_delivery_update
from wob_delivery.auto_fulfillment import create_submitted_documents

class WOBDeliveryOrder(Document):
 def validate(self): validate_order(self)
 def after_insert(self):
  create_submitted_documents(self)
  record_history(self)
 def on_update(self):
  if self.get_doc_before_save(): record_history(self)
  sync_sales_order_status(self)
  publish_delivery_update(self)
 def before_rename(self,*args,**kwargs): assert_delivery_editable(self)
 def on_trash(self):
  assert_company(self.company)
  frappe.db.delete('WOB Delivery Assignment History', {'delivery_order': self.name})
  frappe.db.set_value('Sales Order', {'custom_wob_delivery_order': self.name},
                      {'custom_wob_delivery_order': None, 'custom_wob_delivery_status': None})
  frappe.db.set_value('Payment Entry', {'custom_wob_delivery_order': self.name},
                      {'custom_wob_delivery_order': None})


 def after_delete(self):
  from wob_delivery.live import publish_dashboard_change
  publish_dashboard_change(self,action='deleted')
