"""Explicit local integration check; always rolls back its accounting writes."""
import argparse
import uuid
from decimal import Decimal
import frappe

parser=argparse.ArgumentParser()
parser.add_argument('--site',required=True)
parser.add_argument('--user',required=True)
args=parser.parse_args()
frappe.init(site=args.site,sites_path='.')
frappe.connect()
original=None
invoice_name=None
names=[]
try:
 frappe.set_user(args.user)
 from wob_delivery.mobile import get_driver_deliveries,get_delivery_details,update_delivery_status
 from wob_delivery.payments import collect_payment,_accounting_service
 from wob_delivery.api import get_dashboard
 rows=get_driver_deliveries()
 order=next((r for r in rows if r.delivery_status in ('Out for Delivery','Delivered') and r.payment_type=='Cash on Delivery' and r.get('sales_invoice') and r.get('invoice_outstanding',0)>0),None)
 if not order:raise RuntimeError('No eligible invoice available for rollback check')
 original_status=order.delivery_status
 if original_status=='Out for Delivery':update_delivery_status(order.name,'Delivered')
 invoice_name=order.sales_invoice
 original=frappe.db.get_value('Sales Invoice',invoice_name,'outstanding_amount')
 part=(Decimal(str(original))/2).quantize(Decimal('0.01'))
 key='rollback-'+uuid.uuid4().hex
 first=collect_payment(order.name,str(part),key,str(original))
 names.append(first['payment_entry'])
 assert collect_payment(order.name,str(part),key,str(original))['payment_entry']==names[0]
 assert get_dashboard()['cash_collected_today']>=float(part)
 assert get_delivery_details(order.name)['invoice_outstanding']==first['invoice_outstanding']
 final=collect_payment(order.name,str(first['invoice_outstanding']),'rollback-'+uuid.uuid4().hex,str(first['invoice_outstanding']))
 names.append(final['payment_entry'])
 assert final['invoice_outstanding']==0 and final['invoice_status']=='Paid'
 entries=frappe.get_all('GL Entry',filters={'voucher_type':'Payment Entry','voucher_no':['in',names],'is_cancelled':0},fields=['debit','credit'])
 assert entries and abs(sum(float(x.debit)-float(x.credit) for x in entries))<0.0001
 with _accounting_service():
  locked=frappe.get_doc('WOB Delivery Order',order.name)
  locked.customer_delivery_address='Attempted edit after delivery'
  try:locked.save()
  except frappe.ValidationError as error:
   assert 'locked' in str(error)
  else:raise AssertionError('Administrator was able to edit delivered order')
 print('PASS: partial/full receipts, retry, live summaries, balanced ledger, and delivered lock')
finally:
 frappe.db.rollback()
 if invoice_name:
  assert frappe.db.get_value('Sales Invoice',invoice_name,'outstanding_amount')==original
  assert frappe.db.get_value('WOB Delivery Order',order.name,'delivery_status')==original_status
 assert all(not frappe.db.exists('Payment Entry',n) for n in names)
 print('PASS: original invoice restored and no test payments retained')
 frappe.destroy()
