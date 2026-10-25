import hashlib
import frappe
from frappe.utils import flt, now_datetime, strip_html
from wob_delivery.domain import ACTIVE, TERMINAL, check_transition, amount_to_collect
from wob_delivery.permissions import assert_company, role_kind

SOURCES=('Sales Order','Delivery Note','Sales Invoice')

def lock_record(doctype,name):
 if doctype not in (*SOURCES,'Driver','WOB Delivery Order'): raise ValueError('Invalid lock target')
 frappe.db.sql(f'SELECT name FROM `tab{doctype}` WHERE name=%s FOR UPDATE',(name,))

def active_workload(driver,exclude=None):
 filters={'assigned_driver':driver,'delivery_status':['in',list(ACTIVE)]}
 if exclude: filters['name']=['!=',exclude]
 return frappe.db.count('WOB Delivery Order',filters)

def validate_driver(doc):
 if not doc.assigned_driver:
  if doc.delivery_status in {'Assigned','Out for Delivery','Delivered','Failed'}:
   frappe.throw('Select an assigned driver for this delivery status.')
  return
 lock_record('Driver',doc.assigned_driver)
 driver=frappe.get_doc('Driver',doc.assigned_driver)
 if driver.status!='Active' or not driver.user or not frappe.db.get_value('User',driver.user,'enabled'):
  frappe.throw('The assigned driver must be active and linked to an enabled user.')
 mapping=frappe.db.get_value('WOB Driver Zone Assignment',{'driver':driver.name,'company':doc.company,'delivery_zone':doc.delivery_zone,'active':1},['name','driver_user','availability_status','maximum_active_deliveries'],as_dict=True)
 if not mapping or mapping.driver_user!=driver.user: frappe.throw('Driver has no active user-linked assignment for this company and zone.')
 old=doc.get_doc_before_save()
 taking_assignment=not old or old.assigned_driver!=doc.assigned_driver or old.delivery_status not in ACTIVE
 if taking_assignment and doc.delivery_status in ACTIVE:
  if mapping.availability_status!='Available': frappe.throw('The selected driver is not available.')
  if mapping.maximum_active_deliveries and active_workload(driver.name,doc.name)>=mapping.maximum_active_deliveries:
   frappe.throw('The driver has reached the maximum active deliveries.')
 if doc.delivery_status in {'Pending','Ready for Dispatch'}: frappe.throw('Set status to Assigned when selecting a driver.')

def fulfillment_key(company,refs,lock=True):
 orders={src.name for src in refs if src.doctype=='Sales Order'}
 orders.update(row.get('sales_order') or row.get('against_sales_order') for src in refs for row in src.items)
 orders.discard(None);orders.discard('')
 if len(orders)>1: frappe.throw('Multiple Sales Orders in one fulfillment are not supported in Phase 1.')
 if orders:
  name=next(iter(orders))
  if lock: lock_record('Sales Order',name)
  fulfillment=f'Sales Order::{name}'
 else:
  notes={src.name for src in refs if src.doctype=='Delivery Note'}
  notes.update(row.get('delivery_note') for src in refs for row in src.items)
  notes.discard(None);notes.discard('')
  if len(notes)>1: frappe.throw('Multiple Delivery Notes per task are not supported in Phase 1.')
  fulfillment=f'Delivery Note::{next(iter(notes))}' if notes else f'{refs[0].doctype}::{refs[0].name}'
 return hashlib.sha256(f'{company}::{fulfillment}'.encode()).hexdigest()

def validate_sources(doc):
 refs=[]
 for field,doctype in [('sales_order','Sales Order'),('delivery_note','Delivery Note'),('sales_invoice','Sales Invoice')]:
  if doc.get(field):
   lock_record(doctype,doc.get(field))
   source=frappe.get_doc(doctype,doc.get(field))
   source.check_permission('read')
   if source.docstatus!=1 or source.company!=doc.company: frappe.throw('Sales documents must be submitted and belong to the delivery company.')
   if source.get('is_return'): frappe.throw('Return documents cannot be used for delivery tasks.')
   if source.get('status') in {'Closed','Cancelled','On Hold'}: frappe.throw('Closed, cancelled or held sales documents cannot be dispatched.')
   refs.append(source)
 if not refs: frappe.throw('Link at least one submitted Sales Order, Delivery Note or Sales Invoice.')
 if len({x.customer for x in refs})!=1: frappe.throw('All sales references must belong to the same customer.')
 by_type={x.doctype:x for x in refs}
 invoice=by_type.get('Sales Invoice');note=by_type.get('Delivery Note');order=by_type.get('Sales Order')
 if order:
  for source in [x for x in [note,invoice] if x]:
   if not any(row.get('sales_order')==order.name or row.get('against_sales_order')==order.name for row in source.items):
    frappe.throw('The sales references do not belong to the same fulfillment.')
 if note and invoice and not any(row.get('delivery_note')==note.name for row in invoice.items):
  frappe.throw('The invoice must reference the selected Delivery Note.')
 doc.active_fulfillment_key=fulfillment_key(doc.company,refs) if doc.delivery_status in ACTIVE else None
 if doc.active_fulfillment_key and frappe.db.exists('WOB Delivery Order',{'active_fulfillment_key':doc.active_fulfillment_key,'name':['!=',doc.name or '']}):
  frappe.throw('An active delivery task already exists for this fulfillment.')
 primary=invoice or order or note
 doc.customer=primary.customer
 doc.currency=primary.currency
 if invoice:
  doc.amount_to_collect=amount_to_collect('Sales Invoice',invoice.grand_total,invoice.outstanding_amount,doc.payment_type)
 elif order:
  # A linked submitted invoice is the payment source even if it was not selected
  # on this task. This prevents collecting an already-paid order a second time.
  linked=frappe.db.sql('''SELECT DISTINCT si.name FROM `tabSales Invoice` si JOIN `tabSales Invoice Item` sii ON sii.parent=si.name WHERE si.docstatus=1 AND si.company=%s AND sii.sales_order=%s''',(doc.company,order.name),as_dict=True)
  if linked: frappe.throw('This Sales Order has invoices. Select the matching submitted Sales Invoice to derive its current outstanding balance.')
  doc.amount_to_collect=amount_to_collect('Sales Order',order.grand_total,order.advance_paid,doc.payment_type)
 else:
  frappe.throw('Link the related Sales Invoice or Sales Order to validate the amount to collect.')
 doc.customer_address=primary.get('shipping_address_name') or primary.get('customer_address')
 if not doc.customer_delivery_address:
  doc.customer_delivery_address=strip_html(primary.get('shipping_address') or primary.get('address_display') or '')
 doc.customer_phone_number=primary.get('contact_mobile') or primary.get('contact_phone') or frappe.db.get_value('Customer',doc.customer,'mobile_no')

def assert_delivery_editable(doc):
 if doc.delivery_status=='Delivered':
  frappe.throw('Delivered orders are locked and cannot be edited or reopened.')

def validate_order(doc):
 assert_company(doc.company)
 if not doc.is_new(): lock_record('WOB Delivery Order',doc.name)
 old=doc.get_doc_before_save()
 if old:
  assert_delivery_editable(old)
  assert_company(old.company)
  if old.company!=doc.company: frappe.throw('Delivery company cannot be changed.')
  if any(old.get(k) and old.get(k)!=doc.get(k) for k in ['sales_order','sales_invoice','delivery_note']):
   frappe.throw('Sales references are immutable. Cancel this task and create a new task for a different fulfillment.')
  if old.delivery_status in TERMINAL and old.as_dict()!=doc.as_dict():
   assert_company(doc.company,manager=True)
   if not str(doc.change_reason or '').strip(): frappe.throw('A manager override reason is required to edit a cancelled task.')
  check_transition(old.delivery_status,doc.delivery_status,role_kind()=='Administrator' or 'WOB Delivery Manager' in frappe.get_roles(),doc.change_reason)
  if old.assigned_driver!=doc.assigned_driver:
   if old.assigned_driver and not str(doc.change_reason or '').strip(): frappe.throw('A reassignment reason is required.')
   if old.delivery_status=='Out for Delivery': assert_company(doc.company,manager=True)
  doc.created_by=old.created_by
  doc.completed_at=old.completed_at
 else:
  if doc.delivery_status!='Pending': frappe.throw('New deliveries must start in Pending status.')
  if doc.assigned_driver: frappe.throw('Save and prepare the delivery before assigning a driver.')
  doc.created_by=frappe.session.user
  doc.completed_at=None
  doc.assigned_by=None
  doc.assignment_date_time=None
 if old and doc.delivery_status=='Cancelled':
  for field in ['customer','currency','amount_to_collect','customer_address','customer_phone_number','assigned_by','assignment_date_time']:
   doc.set(field,old.get(field))
  doc.active_fulfillment_key=None
  doc.completed_at=None
  return
 zone=frappe.get_doc('WOB Delivery Zone',doc.delivery_zone)
 if zone.company!=doc.company or not zone.active: frappe.throw('Select an active delivery zone belonging to this company.')
 if doc.latitude is not None and not -90<=flt(doc.latitude)<=90: frappe.throw('Latitude must be between -90 and 90.')
 if doc.longitude is not None and not -180<=flt(doc.longitude)<=180: frappe.throw('Longitude must be between -180 and 180.')
 from wob_delivery.payments import _collection_account,allowed_payment_modes
 modes=allowed_payment_modes(doc)
 if modes:
  currency=frappe.db.get_value('Company',doc.company,'default_currency')
  accounts=[_collection_account(doc.company,currency,mode) for mode in modes]
  doc.allowed_payment_modes=frappe.as_json(modes)
  doc.payment_mode=modes[0] if len(modes)==1 else None
  doc.collection_bank_account=accounts[0][0] if len(modes)==1 else None
  doc.payment_type='Bank Transfer' if all(kind=='Bank' for account,kind in accounts) else 'Cash on Delivery'
 elif modes==[] and doc.payment_type in {'Cash on Delivery','Bank Transfer'}:
  frappe.throw('Tick at least one allowed payment method in Payment & Collection.')
 elif doc.payment_type=='Bank Transfer':frappe.throw('Tick a bank payment method in Payment & Collection.')
 else:doc.collection_bank_account=None
 try:
  validate_sources(doc)
 except ValueError as exc: frappe.throw(str(exc))
 validate_driver(doc)
 if old and old.assigned_driver!=doc.assigned_driver:
  doc.assigned_by=frappe.session.user if doc.assigned_driver else None
  doc.assignment_date_time=now_datetime() if doc.assigned_driver else None
 else:
  if old: doc.assigned_by,doc.assignment_date_time=old.assigned_by,old.assignment_date_time
 if doc.delivery_status=='Delivered' and (not old or old.delivery_status!='Delivered'): doc.completed_at=now_datetime()
 if doc.delivery_status!='Delivered': doc.completed_at=None

def record_history(doc):
 old=doc.get_doc_before_save()
 if old and old.assigned_driver==doc.assigned_driver and old.delivery_status==doc.delivery_status: return
 frappe.local.wob_audit_write=True
 try:
  frappe.get_doc({'doctype':'WOB Delivery Assignment History','delivery_order':doc.name,'company':doc.company,'previous_driver':old.assigned_driver if old else None,'new_driver':doc.assigned_driver,'previous_status':old.delivery_status if old else None,'new_status':doc.delivery_status,'reason':doc.change_reason or ('Delivery created' if not old else 'Status changed'),'changed_by':frappe.session.user,'changed_at':now_datetime()}).insert(ignore_permissions=True)
 finally: frappe.local.wob_audit_write=False
 # Never reuse an earlier reassignment/override reason for a later change.
 doc.db_set('change_reason',None,update_modified=False)
