"""Authenticated driver context and user-scoped assignment events."""
import frappe
from wob_delivery.domain import ACTIVE, check_transition
from wob_delivery.permissions import role_kind, own_driver
from wob_delivery.services import lock_record, record_history
from wob_delivery.sales_order_status import sync_sales_order_status
from frappe.utils import now_datetime
from wob_delivery.payments import payment_summary, payment_summaries


@frappe.whitelist()
def get_context():
 if not role_kind():
  frappe.throw('A delivery role is required.', frappe.PermissionError)
 # Resolve only the current user's own profile; no general Driver read permission needed.
 driver=frappe.db.get_value('Driver',{'user':frappe.session.user,'status':'Active'},
  ['name','full_name','cell_number','employee','status'],as_dict=True)
 assignments=[]
 if driver:
  assignments=frappe.get_list('WOB Delivery Order',
   filters={'assigned_driver':driver.name,'delivery_status':['in',list(ACTIVE)]},
   fields=['name','assigned_driver','assignment_date_time','delivery_status','modified'],
   order_by='assignment_date_time desc',limit_page_length=100)
 return {'driver':driver,'assignments':assignments,'site':frappe.local.site,
  'socketio_port':frappe.conf.get('socketio_port',9000),'developer_mode':bool(frappe.conf.get('developer_mode'))}


DRIVER_SYNC_FIELDS = {
	'assigned_driver', 'delivery_status', 'allowed_payment_modes',
	'payment_mode', 'payment_type', 'amount_to_collect',
	'customer_delivery_address', 'customer_phone_number', 'contact_person',
	'delivery_notes', 'sales_invoice', 'delivery_note', 'scheduled_delivery_date',
	'scheduled_delivery_time'
}


def publish_delivery_update(doc):
	from wob_delivery.live import publish_dashboard_change
	publish_dashboard_change(doc)
	old = doc.get_doc_before_save()
	if old and not any(getattr(old, f, None) != getattr(doc, f, None) for f in DRIVER_SYNC_FIELDS):
		return
	drivers = {d for d in [doc.assigned_driver, old.assigned_driver if old else None] if d}
	for driver in sorted(drivers):
		user = frappe.db.get_value('Driver', driver, 'user')
		if not user: continue
		new_assignment = bool(
			driver == doc.assigned_driver and doc.delivery_status in ACTIVE
			and (not old or old.assigned_driver != driver or old.delivery_status not in ACTIVE)
		)
		frappe.publish_realtime('wob_delivery_update', {
			'name': doc.name, 'delivery_status': doc.delivery_status, 'new_assignment': new_assignment,
			'assignment_date_time': str(getattr(doc, 'assignment_date_time', None) or ''),
			'event_id': f'{doc.name}:{doc.modified}:{driver}',
		}, user=user, after_commit=True)


@frappe.whitelist()
def get_delivery_details(name):
 """Expose packing details only through a delivery the caller may read."""
 order=frappe.get_doc('WOB Delivery Order',name)
 order.check_permission('read')
 result=order.as_dict()
 result.update(payment_summary(order))
 result['items']=[]
 # Prefer the shipment's actual quantities over the full order/invoice quantities.
 for field,doctype in [('delivery_note','Delivery Note'),('sales_invoice','Sales Invoice'),('sales_order','Sales Order')]:
  reference=order.get(field)
  if not reference: continue
  source=frappe.get_doc(doctype,reference)
  if source.company!=order.company or source.customer!=order.customer or source.docstatus!=1:
   frappe.throw('The linked delivery items are unavailable.',frappe.PermissionError)
  # Drivers do not need broad Sales Document permissions: project only packing fields.
  result['items']=[{
   'name':row.name,'item_code':row.item_code,'item_name':row.item_name,
   'qty':row.qty,'uom':row.uom,
  } for row in source.items]
  result['item_source_type']=doctype
  result['item_source_name']=reference
  break
 return result


@frappe.whitelist(methods=['POST'])
def update_delivery_status(name,status):
 """Allow only the assigned driver to start/complete an existing delivery."""
 lock_record('WOB Delivery Order',name)
 doc=frappe.get_doc('WOB Delivery Order',name)
 if not own_driver(doc.assigned_driver):
  frappe.throw('Only the assigned driver can update this delivery.',frappe.PermissionError)
 doc.check_permission('read')
 if status not in {'Out for Delivery','Delivered'}:
  frappe.throw('Drivers can only start or complete an assigned delivery.')
 try: check_transition(doc.delivery_status,status)
 except ValueError as exc: frappe.throw(str(exc))
 if doc.delivery_status==status: return doc.as_dict()
 # This action changes logistics fields only; never resave linked sales/stock documents.
 doc.load_doc_before_save()
 values={'delivery_status':status}
 if status=='Delivered':
  values.update(completed_at=now_datetime(),active_fulfillment_key=None)
 doc.db_set(values,notify=False)
 record_history(doc)
 sync_sales_order_status(doc)
 publish_delivery_update(doc)
 doc.notify_update()
 return doc.as_dict()


@frappe.whitelist()
def get_driver_deliveries(driver=None,status=None,company=None):
 profile=frappe.db.get_value('Driver',{'user':frappe.session.user,'status':'Active'},'name')
 if not profile or (driver and driver!=profile):
  frappe.throw('Only your own assigned deliveries are available.',frappe.PermissionError)
 filters={'assigned_driver':profile}
 if status:filters['delivery_status']=status
 if company:filters['company']=company
 fields=['name','company','scheduled_delivery_date','scheduled_delivery_time','delivery_status','customer',
  'customer_phone_number','customer_delivery_address','delivery_zone','assigned_driver',
  'assignment_date_time','payment_type','payment_mode','allowed_payment_modes','amount_to_collect','currency','sales_order','sales_invoice','delivery_note']
 rows=frappe.get_list('WOB Delivery Order',filters=filters,fields=fields,order_by='creation desc',limit_page_length=100)
 summaries=payment_summaries(rows)
 for row in rows:row.update(summaries[row.name])
 return rows
