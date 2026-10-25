"""Permission-scoped delivery aggregates and canonical staff actions."""
from datetime import timedelta
from math import ceil
import frappe
from frappe.utils import cint, getdate, nowdate, now_datetime, get_system_timezone
from wob_delivery.domain import ACTIVE, STATUSES
from wob_delivery.permissions import assert_company, role_kind
from wob_delivery.services import lock_record

DOCTYPE = 'WOB Delivery Order'
SORT_FIELDS = {'name', 'customer', 'company', 'delivery_zone', 'assigned_driver', 'delivery_status', 'scheduled_delivery_date', 'modified', 'amount_to_collect'}
ORDER_FIELDS = ['name', 'company', 'customer', 'delivery_zone', 'assigned_driver', 'delivery_status', 'scheduled_delivery_date', 'currency', 'amount_to_collect', 'sales_order', 'sales_invoice', 'delivery_note', 'payment_type', 'modified', 'completed_at']


def page_options(page, page_size, sort_by, sort_order):
 sort_order = str(sort_order or 'asc').lower()
 if sort_by not in SORT_FIELDS or sort_order not in {'asc', 'desc'}:
  frappe.throw('Invalid delivery sort option.')
 return max(1, cint(page)), min(100, max(1, cint(page_size))), sort_by, sort_order


def intersect_filters(filters, completed_today=0, issues_only=0, today=None):
 result = [[key, '=', value] if not isinstance(value, (list, tuple)) else [key, *value] for key, value in filters.items()]
 if cint(issues_only): result.append(['delivery_status', 'in', ['Failed', 'Rescheduled']])
 if cint(completed_today):
  day = getdate(today or nowdate())
  result.extend([['delivery_status', '=', 'Delivered'], ['completed_at', '>=', str(day)], ['completed_at', '<', str(day + timedelta(days=1))]])
 return result


def group_rows(rows, field, drivers):
 groups = {}
 for row in rows:
  key = row.get(field) or None
  if key not in groups:
   label = drivers.get(key, key) or ('Unassigned' if field == 'assigned_driver' else 'Unspecified')
   groups[key] = {field:key, 'label':label, 'count':0, 'counts':{status:0 for status in STATUSES}, 'active_count':0, 'delivered_today':0}
   if field == 'assigned_driver': groups[key]['driver_name'] = label
  group = groups[key]
  count = int(row['count'])
  group['count'] += count
  group['counts'][row['delivery_status']] = group['counts'].get(row['delivery_status'], 0) + count
  group['active_count'] += count if row['delivery_status'] in ACTIVE else 0
  group['delivered_today'] += int(row.get('delivered_today') or 0)
 return sorted(groups.values(), key=lambda row: (-row['count'], str(row['label'])))


def get_dashboard(company=None, delivery_zone=None, driver=None, from_date=None, to_date=None, status=None,
                  customer_search=None, order_search=None, page=1, page_size=25,
                  sort_by='scheduled_delivery_date', sort_order='asc', completed_today=0, issues_only=0):
 from wob_delivery.api import delivery_filters
 filters = intersect_filters(delivery_filters(company, delivery_zone, driver, from_date, to_date, status), completed_today, issues_only)
 page, page_size, sort_by, sort_order = page_options(page, page_size, sort_by, sort_order)
 # Installed Frappe v16 get_list(run=False) builds a permission-checked QB query.
 # Reuse it as a subquery, so every SQL aggregate shares all record/user permissions.
 scope = frappe.get_list(DOCTYPE, filters=filters, fields=['name'], limit_page_length=0, order_by='', run=False)
 scope_sql, params = scope.walk()
 where = f'd.name IN ({scope_sql})'
 if customer_search:
  params['dash_customer'] = '%' + str(customer_search).strip()[:140] + '%'
  where += ' AND (d.customer LIKE %(dash_customer)s OR EXISTS (SELECT 1 FROM `tabCustomer` c WHERE c.name=d.customer AND c.customer_name LIKE %(dash_customer)s))'
 if order_search:
  params['dash_order'] = '%' + str(order_search).strip()[:140] + '%'
  where += ' AND d.name LIKE %(dash_order)s'
 today = getdate(nowdate())
 params.update(dash_start=str(today), dash_end=str(today + timedelta(days=1)))
 today_expr = "d.delivery_status='Delivered' AND d.completed_at >= %(dash_start)s AND d.completed_at < %(dash_end)s"
 def query(fields, suffix=''):
  return frappe.db.sql(f'SELECT {fields} FROM `tabWOB Delivery Order` d WHERE {where} {suffix}', params, as_dict=True)
 statuses = query(f'd.delivery_status, COUNT(*) AS count, SUM({today_expr}) AS delivered_today', 'GROUP BY d.delivery_status')
 counts = {value:0 for value in STATUSES}
 for row in statuses: counts[row.delivery_status] = int(row['count'])
 total = sum(counts.values())
 page = min(page, max(1, ceil(total/page_size)))
 params.update(dash_limit=page_size, dash_offset=(page-1)*page_size)
 orders = query(', '.join('d.`'+field+'`' for field in ORDER_FIELDS), f'ORDER BY d.`{sort_by}` {sort_order}, d.name asc LIMIT %(dash_limit)s OFFSET %(dash_offset)s')
 raw_groups = {field:query(f'd.`{field}`, d.delivery_status, COUNT(*) AS count, SUM({today_expr}) AS delivered_today', f'GROUP BY d.`{field}`, d.delivery_status') for field in ('delivery_zone', 'assigned_driver', 'company')}
 driver_names = {row.get('assigned_driver') for row in raw_groups['assigned_driver'] if row.get('assigned_driver')}
 drivers = {row.name:row.full_name for row in frappe.get_all('Driver', filters={'name':['in',list(driver_names)]}, fields=['name','full_name'], limit_page_length=0)} if driver_names else {}
 zone_ids = {row.get('delivery_zone') for row in raw_groups['delivery_zone'] if row.get('delivery_zone')}
 zones = {row.name:row.zone_name for row in frappe.get_all('WOB Delivery Zone', filters={'name':['in',list(zone_ids)]}, fields=['name','zone_name'], limit_page_length=0)} if zone_ids else {}
 customer_ids = list({row.customer for row in orders if row.customer})
 customers = {row.name:row.customer_name for row in frappe.get_all('Customer', filters={'name':['in',customer_ids]}, fields=['name','customer_name'], limit_page_length=0)} if customer_ids else {}
 for order in orders:
  order['driver_name'] = drivers.get(order.assigned_driver) or order.assigned_driver or 'Unassigned'
  order['customer_name'] = customers.get(order.customer) or order.customer
  order['zone_name'] = zones.get(order.delivery_zone) or order.delivery_zone
 # Financial aggregates use the entire filtered scope, deduplicating invoices.
 # Invoice company/customer/submission checks match payment_summaries.
 collections = frappe.db.sql(f'''SELECT COALESCE(SUM(CASE WHEN a.account_type='Cash' THEN p.paid_amount ELSE 0 END),0) AS total,
  COALESCE(SUM(CASE WHEN a.account_type='Bank' THEN p.paid_amount ELSE 0 END),0) AS bank_total FROM `tabPayment Entry` p JOIN `tabAccount` a ON a.name=p.paid_to
  WHERE p.docstatus=1 AND p.posting_date=%(dash_start)s AND EXISTS
  (SELECT 1 FROM `tabWOB Delivery Order` d WHERE {where} AND d.name=p.custom_wob_delivery_order)''', params, as_dict=True)[0]
 balance = frappe.db.sql(f'''SELECT COALESCE(SUM(i.outstanding_amount),0) AS total FROM `tabSales Invoice` i
  WHERE i.docstatus=1 AND i.outstanding_amount>0 AND EXISTS
  (SELECT 1 FROM `tabWOB Delivery Order` d WHERE {where} AND d.sales_invoice=i.name
   AND d.payment_type IN ('Cash on Delivery','Bank Transfer') AND d.company=i.company AND d.customer=i.customer)''', params, as_dict=True)[0].total
 return {'counts':counts, 'delivered_today':sum(int(row.delivered_today or 0) for row in statuses),
         'by_zone':group_rows(raw_groups['delivery_zone'], 'delivery_zone', zones),
         'by_driver':group_rows(raw_groups['assigned_driver'], 'assigned_driver', drivers),
         'by_company':group_rows(raw_groups['company'], 'company', drivers), 'orders':orders,
         'cash_collected_today':float(collections.get('total') or 0), 'bank_collected_today':float(collections.get('bank_total') or 0), 'invoice_balance_due':float(balance or 0),
         'pagination':{'page':page, 'page_size':page_size, 'total':total, 'total_pages':ceil(total/page_size)},
         'server_time':str(now_datetime()), 'timezone':get_system_timezone(), 'can_manage':role_kind() in {'Administrator','Manager'}}


@frappe.whitelist()
def get_task_details(name):
 doc = frappe.get_doc(DOCTYPE, name)
 doc.check_permission('read')
 fields = ['name','previous_driver','new_driver','previous_status','new_status','reason','changed_by','changed_at']
 # Driver users can read their task's history after its read check, even though
 # the standalone history DocType is staff-only.
 timeline = frappe.get_all('WOB Delivery Assignment History', filters={'delivery_order':doc.name, 'company':doc.company}, fields=fields, order_by='changed_at asc, creation asc', limit_page_length=0)
 from wob_delivery.payments import payment_summary
 order = doc.as_dict()
 order.update(payment_summary(doc))
 if doc.assigned_driver: order['driver_name'] = frappe.db.get_value('Driver',doc.assigned_driver,'full_name') or doc.assigned_driver
 else: order['driver_name'] = 'Unassigned'
 return {'order':order, 'timeline':timeline}


@frappe.whitelist(methods=['POST'])
def perform_action(name, action, driver=None, reason=None):
 targets = {'ready':'Ready for Dispatch', 'assign':'Assigned', 'dispatch':'Out for Delivery', 'delivered':'Delivered', 'failed':'Failed'}
 if action not in targets: frappe.throw('Invalid delivery action.')
 lock_record(DOCTYPE, name)
 doc = frappe.get_doc(DOCTYPE, name)
 assert_company(doc.company)
 if doc.delivery_status == 'Delivered': frappe.throw('Delivered orders are locked and cannot be changed.')
 doc.check_permission('write')
 if action == 'assign':
  if not driver: frappe.throw('Select a driver.')
  doc.assigned_driver = driver
 if action == 'failed' and not str(reason or '').strip(): frappe.throw('Enter a failure reason.')
 doc.change_reason = str(reason or '').strip()
 doc.delivery_status = targets[action]
 doc.save()
 return get_task_details(name)
