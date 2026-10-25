"""Permission-scoped dashboard invalidation through Frappe user rooms."""
from collections import defaultdict
from uuid import uuid4
import frappe

STAFF_ROLES={'System Manager','WOB Delivery Administrator','WOB Delivery Manager','WOB Delivery Dispatcher'}
ADMIN_ROLES={'System Manager','WOB Delivery Administrator'}


def _value(doc,field,default=None):
 return doc.get(field,default) if hasattr(doc,'get') else getattr(doc,field,default)


def dashboard_recipients(doc):
 """Bulk-select staff by company, then retain all framework record restrictions."""
 company=_value(doc,'company')
 roles=frappe.get_all('Has Role',filters={'role':['in',sorted(STAFF_ROLES)],'parenttype':'User'},fields=['parent','role'])
 users=defaultdict(set)
 for row in roles:users[row.parent].add(row.role)
 users['Administrator'].add('System Manager')
 enabled=set(frappe.get_all('User',filters={'name':['in',list(users)],'enabled':1},pluck='name'))
 restrictions=frappe.get_all('User Permission',filters={'user':['in',list(enabled)],'allow':'Company','for_value':company},fields=['user']) if enabled else []
 allowed={row.user for row in restrictions}
 recipients=[]
 for user in sorted(enabled):
  if users[user].intersection(ADMIN_ROLES) or user in allowed:
   # Company scope alone is insufficient: Customer/Zone user permissions and
   # other Frappe record restrictions must also hold for this recipient.
   if frappe.has_permission('WOB Delivery Order',ptype='read',doc=doc,user=user):
    recipients.append(user)
 return recipients


def classify_change(doc):
 if _value(getattr(doc,'flags',{}),'in_insert',False):return 'created'
 getter=getattr(doc,'get_doc_before_save',None)
 old=getter() if callable(getter) else None
 if not old:return 'created'
 if _value(old,'assigned_driver')!=_value(doc,'assigned_driver'):
  return 'reassigned' if _value(old,'assigned_driver') else 'assigned'
 if _value(old,'delivery_status')!=_value(doc,'delivery_status'):
  return {'Ready for Dispatch':'ready','Out for Delivery':'dispatched','Delivered':'delivered',
   'Failed':'failed','Rescheduled':'rescheduled','Cancelled':'cancelled'}.get(_value(doc,'delivery_status'),'updated')
 return 'updated'


def publish_dashboard_change(doc,action=None):
 company=_value(doc,'company')
 name=_value(doc,'name')
 # Incomplete documents/test doubles are not publishable business records.
 if not isinstance(company,str) or not company or not isinstance(name,str) or not name:return
 action=action or classify_change(doc)
 revision=str(_value(doc,'modified') or '')
 payload={'delivery_id':name,'company':company,'action':action,'revision':revision,
  'event_id':f'{name}:{revision}:{action}:{uuid4().hex}'}
 for user in dashboard_recipients(doc):
  frappe.publish_realtime('wob_delivery_changed',payload,user=user,after_commit=True)


def payment_changed(doc,method=None):
 """Reconcile COD display when a linked receipt is posted or canceled anywhere."""
 name=_value(doc,'custom_wob_delivery_order')
 if not name or not isinstance(name,str) or not frappe.db.exists('WOB Delivery Order',name):return
 order=frappe.get_doc('WOB Delivery Order',name)
 publish_dashboard_change(order,action='payment_recorded' if doc.docstatus==1 else 'payment_cancelled')
