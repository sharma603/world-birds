import frappe
from frappe.utils import cint, getdate, nowdate, strip_html
from wob_delivery.domain import STATUSES, ACTIVE, amount_to_collect
from wob_delivery.permissions import assert_company, role_kind, companies
from wob_delivery.services import active_workload, fulfillment_key, lock_record, assert_delivery_editable
from wob_delivery.payments import payment_summaries


def delivery_filters(company=None,delivery_zone=None,driver=None,from_date=None,to_date=None,status=None):
 if not role_kind(): frappe.throw('A WOB Delivery role is required.',frappe.PermissionError)
 filters={}
 if company:
  if company!='__unassigned__' and role_kind()!='Driver': assert_company(company)
  filters['company']=['is','not set'] if company=='__unassigned__' else company
 if delivery_zone: filters['delivery_zone']=['is','not set'] if delivery_zone=='__unassigned__' else delivery_zone
 if driver: filters['assigned_driver']=['is','not set'] if driver=='__unassigned__' else driver
 if status:
  if status not in STATUSES: frappe.throw('Invalid delivery status.')
  filters['delivery_status']=status
 if from_date and to_date:
  if getdate(from_date)>getdate(to_date): frappe.throw('From date cannot be after To date.')
  filters['scheduled_delivery_date']=['between',[getdate(from_date),getdate(to_date)]]
 elif from_date: filters['scheduled_delivery_date']=['>=',getdate(from_date)]
 elif to_date: filters['scheduled_delivery_date']=['<=',getdate(to_date)]
 return filters

ORDER_FIELDS=['name','company','customer','delivery_zone','assigned_driver','delivery_status','scheduled_delivery_date','currency','amount_to_collect']

@frappe.whitelist()
def get_dashboard(company=None,delivery_zone=None,driver=None,from_date=None,to_date=None,status=None,
                  customer_search=None,order_search=None,page=1,page_size=25,
                  sort_by='scheduled_delivery_date',sort_order='asc',completed_today=0,issues_only=0):
 from wob_delivery.dashboard import get_dashboard as dashboard
 return dashboard(company,delivery_zone,driver,from_date,to_date,status,customer_search,order_search,
                  page,page_size,sort_by,sort_order,completed_today,issues_only)

@frappe.whitelist()
def get_driver_recommendations(company,delivery_zone):
 assert_company(company)
 zone=frappe.get_doc('WOB Delivery Zone',delivery_zone)
 if zone.company!=company or not zone.active: frappe.throw('Select an active zone for this company.')
 mappings=frappe.get_list('WOB Driver Zone Assignment',filters={'company':company,'delivery_zone':delivery_zone,'active':1},fields=['name','driver','driver_user','assignment_type','availability_status','maximum_active_deliveries'],limit_page_length=0)
 driver_ids=list({row.driver for row in mappings})
 drivers={row.name:row for row in frappe.get_all('Driver',filters={'name':['in',driver_ids]},fields=['name','full_name','user','status'],limit_page_length=0)} if driver_ids else {}
 users=list({row.user for row in drivers.values() if row.user})
 enabled=set(frappe.get_all('User',filters={'name':['in',users],'enabled':1},pluck='name',limit_page_length=0)) if users else set()
 # Capacity remains global, while the displayed workload is company-scoped.
 workload=frappe.get_all('WOB Delivery Order',filters={'assigned_driver':['in',driver_ids],'delivery_status':['in',list(ACTIVE)]},fields=['assigned_driver','company',{'COUNT':'name','as':'count'}],group_by='assigned_driver, company',limit_page_length=0) if driver_ids else []
 global_counts={}
 company_counts={}
 for row in workload:
  global_counts[row.assigned_driver]=global_counts.get(row.assigned_driver,0)+row['count']
  if row.company==company: company_counts[row.assigned_driver]=company_counts.get(row.assigned_driver,0)+row['count']
 result=[]
 for row in mappings:
  driver=drivers.get(row.driver)
  if not driver or driver.status!='Active' or driver.user!=row.driver_user or driver.user not in enabled: continue
  row['active_deliveries']=company_counts.get(row.driver,0)
  row['driver_name']=driver.full_name
  row['can_assign']=row.availability_status=='Available' and (not row.maximum_active_deliveries or global_counts.get(row.driver,0)<row.maximum_active_deliveries)
  result.append(row)
 return sorted(result,key=lambda x:(not x.can_assign,x.assignment_type!='Primary',x.active_deliveries))

@frappe.whitelist()
def driver_query(doctype, txt, searchfield, start, page_len, filters):
 # Reuse recommendation permissions and eligibility; never offer unrelated drivers.
 if doctype != 'Driver': frappe.throw('Invalid driver search type.')
 filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
 company, zone = filters.get('company'), filters.get('delivery_zone')
 if not company or not zone: return []
 rows = get_driver_recommendations(company, zone)
 text = (txt or '').casefold()
 matches = [(row['driver'], row['driver_name']) for row in rows
            if row['can_assign'] and (text in row['driver'].casefold() or text in row['driver_name'].casefold())]
 offset, limit = max(0, cint(start)), min(100, max(1, cint(page_len)))
 return matches[offset:offset + limit]

@frappe.whitelist()
def get_eligible_orders(company=None,source_type='Sales Invoice'):
 if company:
  assert_company(company)
  company_filter=company
 else:
  if role_kind() not in {'Administrator','Manager'}:
   frappe.throw('A delivery staff role is required.',frappe.PermissionError)
  allowed=sorted(companies())
  if not allowed: return []
  company_filter=['in',allowed]
 if source_type not in {'Sales Order','Sales Invoice','Delivery Note'}: frappe.throw('Invalid sales document type.')
 filters={'company':company_filter,'docstatus':1,'status':['not in',['Closed','Cancelled','On Hold']]}
 if source_type=='Sales Order': filters['per_delivered']=['<',100]
 rows=frappe.get_list(source_type,filters=filters,fields=['name','company','customer','currency','grand_total'],order_by='modified desc',limit_page_length=100)
 # Final source/fulfillment validation is performed atomically when a task saves.
 result=[]
 for row in rows:
  source=frappe.get_doc(source_type,row.name);source.check_permission('read')
  if source.get('is_return'): continue
  assert_company(source.company)
  source_field={'Sales Order':'sales_order','Sales Invoice':'sales_invoice','Delivery Note':'delivery_note'}[source_type]
  if frappe.db.exists('WOB Delivery Order',{'company':source.company,source_field:row.name,'delivery_status':'Delivered','docstatus':['!=',2]}): continue
  try: key=fulfillment_key(source.company,[source],lock=False)
  except frappe.ValidationError: continue
  if not frappe.db.exists('WOB Delivery Order',{'active_fulfillment_key':key}): result.append(row)
 return result

@frappe.whitelist()
def get_source_preview(company,source_type,source_name):
 assert_company(company)
 if source_type not in {'Sales Order','Sales Invoice','Delivery Note'}: frappe.throw('Invalid sales document type.')
 doc=frappe.get_doc(source_type,source_name);doc.check_permission('read')
 if doc.company!=company or doc.docstatus!=1: frappe.throw('Select a submitted sales document from this company.')
 return {'customer':doc.customer,'customer_delivery_address':strip_html(doc.get('shipping_address') or doc.get('address_display') or ''),'customer_phone_number':doc.get('contact_mobile') or doc.get('contact_phone'),'currency':doc.currency}

@frappe.whitelist()
def sync_fulfillment_documents(delivery_order):
 company=frappe.db.get_value('WOB Delivery Order',delivery_order,'company')
 assert_company(company)
 lock_record('WOB Delivery Order',delivery_order)
 doc=frappe.get_doc('WOB Delivery Order',delivery_order)
 assert_delivery_editable(doc)
 if not doc.sales_order:
  return {'synced':False}

 updated={}
 if not doc.delivery_note:
  dn=frappe.db.sql('''
   SELECT DISTINCT dni.parent 
   FROM `tabDelivery Note Item` dni
   JOIN `tabDelivery Note` dn ON dn.name=dni.parent
   WHERE dni.against_sales_order=%s AND dn.docstatus=1 AND dn.company=%s
   ORDER BY dn.creation DESC LIMIT 1
  ''',(doc.sales_order,doc.company),as_dict=True)
  if dn:
   updated['delivery_note']=dn[0]['parent']
   doc.db_set('delivery_note',dn[0]['parent'],update_modified=False)

 if not doc.sales_invoice:
  si=frappe.db.sql('''
   SELECT DISTINCT sii.parent 
   FROM `tabSales Invoice Item` sii
   JOIN `tabSales Invoice` si ON si.name=sii.parent
   WHERE sii.sales_order=%s AND si.docstatus=1 AND si.company=%s
   ORDER BY si.creation DESC LIMIT 1
  ''',(doc.sales_order,doc.company),as_dict=True)
  if si:
   updated['sales_invoice']=si[0]['parent']
   doc.db_set('sales_invoice',si[0]['parent'],update_modified=False)

 if updated:
  from wob_delivery.services import validate_sources
  try:
   validate_sources(doc)
   doc.db_set({
    'amount_to_collect':doc.amount_to_collect,
    'currency':doc.currency,
    'active_fulfillment_key':doc.active_fulfillment_key
   },update_modified=False)
  except Exception:
   pass
  from wob_delivery.live import publish_dashboard_change
  publish_dashboard_change(doc, action='fulfillment')
  return {'synced':True,'updated':updated}
 return {'synced':False}

@frappe.whitelist()
def create_fulfillment_documents(delivery_order):
 lock_record('WOB Delivery Order',delivery_order)
 doc=frappe.get_doc('WOB Delivery Order',delivery_order)
 assert_company(doc.company)
 assert_delivery_editable(doc)
 if not doc.sales_order:
  frappe.throw('Delivery Order does not have a linked Sales Order.')
 if doc.delivery_note and doc.sales_invoice:
  return {'delivery_note':doc.delivery_note,'sales_invoice':doc.sales_invoice}
 from wob_delivery.auto_fulfillment import create_submitted_documents
 before=(doc.delivery_note,doc.sales_invoice)
 create_submitted_documents(doc)
 doc.reload()
 if before!=(doc.delivery_note,doc.sales_invoice):
  from wob_delivery.live import publish_dashboard_change
  publish_dashboard_change(doc, action='fulfillment')
 return {'delivery_note':doc.delivery_note,'sales_invoice':doc.sales_invoice}

