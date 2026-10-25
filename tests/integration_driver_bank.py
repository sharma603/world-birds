"""Explicit accounting integration check. Run from bench/sites; always rolls back."""
import frappe,uuid,argparse
from decimal import Decimal
parser=argparse.ArgumentParser(description='Bank receipt accounting verification; all writes roll back.')
parser.add_argument('--site',required=True)
args=parser.parse_args()
frappe.init(site=args.site,sites_path='.')
frappe.connect()
receipts=[];bank_name=None;invoice_name=None;original=None;fixture_invoice=None;fixture_order=None
try:
 from wob_delivery.payments import collect_payment,get_collection_options
 from wob_delivery.api import get_dashboard
 frappe.set_user('Administrator')
 orders=frappe.get_all('WOB Delivery Order',filters={'delivery_status':'Delivered','payment_type':'Cash on Delivery'},fields=['name','company','customer','currency','sales_invoice','assigned_driver'])
 order=next((row for row in orders if row.sales_invoice and frappe.db.get_value('Sales Invoice',row.sales_invoice,'outstanding_amount')>0),None)
 if not order:
  assert orders,'No delivered driver order for test setup'
  base=orders[0]
  invoice=frappe.copy_doc(frappe.get_doc('Sales Invoice',base.sales_invoice))
  invoice.set('payments',[])
  invoice.set('payment_schedule',[])
  invoice.posting_date=frappe.utils.nowdate()
  invoice.due_date=frappe.utils.nowdate()
  invoice.is_pos=0
  invoice.update_stock=0
  invoice.paid_amount=0
  invoice.base_paid_amount=0
  invoice.write_off_amount=0
  invoice.outstanding_amount=0
  invoice.status='Draft'
  for row in invoice.items:
   for field in ['sales_order','so_detail','delivery_note','dn_detail']:row.set(field,None)
  invoice.insert();invoice.submit();fixture_invoice=invoice.name
  fixture=frappe.copy_doc(frappe.get_doc('WOB Delivery Order',base.name))
  fixture.name='WOB-BANK-ROLLBACK-'+uuid.uuid4().hex[:10]
  fixture.sales_order=None;fixture.delivery_note=None;fixture.sales_invoice=invoice.name
  fixture.active_fulfillment_key=None;fixture.docstatus=0
  fixture.db_insert();fixture_order=fixture.name
  order=fixture

 user=frappe.db.get_value('Driver',order.assigned_driver,'user')
 invoice_name=order.sales_invoice
 original=frappe.db.get_value('Sales Invoice',invoice_name,'outstanding_amount')
 mapping=frappe.db.get_value('Mode of Payment Account',{'parent':'Bank Transfer','company':order.company},'name')
 old_account=frappe.db.get_value('Mode of Payment Account',mapping,'default_account')
 bank=frappe.get_doc({'doctype':'Account','account_name':'WOB rollback bank '+uuid.uuid4().hex[:8],'company':order.company,'parent_account':frappe.db.get_value('Account',{'company':order.company,'account_name':'Bank Accounts','is_group':1},'name'),'account_type':'Bank','account_currency':order.currency,'is_group':0})
 bank.insert();bank_name=bank.name
 frappe.db.set_value('Mode of Payment Account',mapping,'default_account',bank.name)
 frappe.set_user(user)
 options=get_collection_options(order.name)
 assert any(x['type']=='Bank' for x in options['methods'])
 before=get_dashboard(driver=order.assigned_driver)
 amount=(Decimal(str(original))/2).quantize(Decimal('.01'))
 key='rollback-bank-'+uuid.uuid4().hex
 ref='WOB-ROLLBACK-'+uuid.uuid4().hex
 first=collect_payment(order.name,str(amount),key,str(original),'Bank Transfer',ref,options['today'])
 receipts.append(first['payment_entry'])
 payment=frappe.get_doc('Payment Entry',receipts[0])
 assert payment.docstatus==1 and payment.paid_to==bank.name and payment.mode_of_payment=='Bank Transfer' and payment.reference_no==ref
 assert Decimal(str(first['invoice_outstanding']))==Decimal(str(original))-amount
 assert collect_payment(order.name,str(amount),key,str(original),'Bank Transfer',ref,options['today'])['payment_entry']==receipts[0]
 after=get_dashboard(driver=order.assigned_driver)
 assert after['cash_collected_today']==before['cash_collected_today']
 assert abs(after['bank_collected_today']-before['bank_collected_today']-float(amount))<.001
 final=collect_payment(order.name,str(first['invoice_outstanding']),'rollback-bank-'+uuid.uuid4().hex,str(first['invoice_outstanding']),'Bank Transfer','FINAL-'+ref,options['today'])
 receipts.append(final['payment_entry'])
 assert final['invoice_outstanding']==0 and final['invoice_status']=='Paid'
 entries=frappe.get_all('GL Entry',filters={'voucher_type':'Payment Entry','voucher_no':['in',receipts],'is_cancelled':0},fields=['debit','credit'])
 assert entries and abs(sum(float(x.debit)-float(x.credit) for x in entries))<.0001
 print('PASS: bank partial/full posting, references, retry dedupe, Paid invoice, bank/cash separation, balanced ledger')
finally:
 frappe.db.rollback()
 if invoice_name and not fixture_invoice:assert frappe.db.get_value('Sales Invoice',invoice_name,'outstanding_amount')==original
 if bank_name:
  assert not frappe.db.exists('Account',bank_name)
  assert frappe.db.get_value('Mode of Payment Account',mapping,'default_account')==old_account
 if fixture_invoice:assert not frappe.db.exists('Sales Invoice',fixture_invoice)
 if fixture_order:assert not frappe.db.exists('WOB Delivery Order',fixture_order)
 assert all(not frappe.db.exists('Payment Entry',name) for name in receipts)
 print('PASS: rollback restored invoice, payment mapping, ledger and temporary account')
 frappe.destroy()
