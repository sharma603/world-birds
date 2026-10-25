"""Driver-confirmed cash and bank receipts, posted through ERPNext's accounting workflow."""
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import re
import json
import frappe
from frappe.utils import nowdate, getdate
from wob_delivery.permissions import own_driver
from wob_delivery.services import lock_record


def setup_fields():
 from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
 create_custom_fields({'Payment Entry':[
  {'fieldname':'custom_wob_delivery_order','label':'Delivery Order','fieldtype':'Link',
   'options':'WOB Delivery Order','insert_after':'remarks','read_only':1,'no_copy':1},
  {'fieldname':'custom_wob_collected_by','label':'Collected By','fieldtype':'Link',
   'options':'User','insert_after':'custom_wob_delivery_order','read_only':1,'no_copy':1},
  {'fieldname':'custom_wob_collection_request','label':'Collection Request ID','fieldtype':'Data',
   'insert_after':'custom_wob_collected_by','read_only':1,'hidden':1,'unique':1,'no_copy':1},
 ]})


def validated_amount(value,outstanding,precision=2):
 try:
  amount=Decimal(str(value))
  balance=Decimal(str(outstanding))
  if not amount.is_finite() or not balance.is_finite(): raise ValueError
  unit=Decimal(1).scaleb(-precision)
  if amount<=0 or amount>balance or amount!=amount.quantize(unit): raise ValueError
 except (InvalidOperation,ValueError,TypeError):
  frappe.throw('Enter a positive amount no greater than the invoice balance, using the currency precision.')
 return amount


@contextmanager
def _accounting_service():
 # Never expose this context through an RPC. All identifiers/accounts are derived
 # from the locked, authorized delivery before entering it. Preserve the real SID.
 user=frappe.session.user
 state={key:getattr(frappe.local,key,None) for key in ('user_perms','role_permissions','new_doc_templates')}
 try:
  frappe.session.user='Administrator'
  frappe.local.user_perms=None
  frappe.local.role_permissions={}
  frappe.local.new_doc_templates={}
  yield
 finally:
  frappe.session.user=user
  for key,value in state.items():setattr(frappe.local,key,value)


def _cash_account(company,currency):
 if not frappe.db.exists('Mode of Payment',{'name':'Cash','type':'Cash','enabled':1}):
  frappe.throw('Configure an enabled Cash mode of payment first.')
 account=frappe.db.get_value('Mode of Payment Account',{'parent':'Cash','company':company},'default_account')
 account=account or frappe.db.get_value('Company',company,'default_cash_account')
 data=frappe.db.get_value('Account',account,['company','account_type','account_currency','is_group','disabled'],as_dict=True) if account else None
 if not data or data.company!=company or data.account_type!='Cash' or data.is_group or data.disabled:
  frappe.throw('Configure a valid Cash account for this company first.')
 if data.account_currency!=currency or frappe.db.get_value('Company',company,'default_currency')!=currency:
  frappe.throw('Mobile cash collection currently requires invoice and cash-account currency to match company currency.')
 return account


def _collection_account(company,currency,mode_of_payment):
 if mode_of_payment=='Cash':return _cash_account(company,currency),'Cash'
 kind=frappe.db.get_value('Mode of Payment',{'name':mode_of_payment,'enabled':1},'type')
 if kind not in {'Cash','Bank','General','Phone'}:frappe.throw('Select an enabled Cash or Bank mode of payment.')
 account=frappe.db.get_value('Mode of Payment Account',{'parent':mode_of_payment,'company':company},'default_account')
 data=frappe.db.get_value('Account',account,['company','account_type','account_currency','is_group','disabled'],as_dict=True) if account else None
 if not data or data.company!=company or (data.account_type not in {'Cash','Bank'} or (kind in {'Cash','Bank'} and data.account_type!=kind)) or data.is_group or data.disabled:
  frappe.throw('Configure a valid company Bank account for this payment mode. A Cash account cannot receive bank transfers.')
 if data.account_currency!=currency or frappe.db.get_value('Company',company,'default_currency')!=currency:
  frappe.throw('Mobile bank collection requires invoice and bank-account currency to match company currency.')
 return account,data.account_type


def allowed_payment_modes(order):
 raw=order.get('allowed_payment_modes')
 if raw is None or raw=='':return [order.get('payment_mode')] if order.get('payment_mode') else None
 try:
  values=json.loads(raw) if isinstance(raw,str) else raw
  if not isinstance(values,list) or len(values)>100 or any(not isinstance(name,str) or not name.strip() or len(name)>140 for name in values):raise ValueError
 except (ValueError,TypeError):frappe.throw('Invalid checked payment methods. Refresh and tick the allowed methods again.')
 return list(dict.fromkeys(values))


def collection_methods(company,currency,modes):
 methods=[]
 company_currency=frappe.db.get_value('Company',company,'default_currency')
 for mode in modes:
  account=frappe.db.get_value('Mode of Payment Account',{'parent':mode.name,'company':company},'default_account')
  if mode.type=='Cash':account=account or frappe.db.get_value('Company',company,'default_cash_account')
  data=frappe.db.get_value('Account',account,['company','account_type','account_currency','is_group','disabled'],as_dict=True) if account else None
  valid=bool(mode.type in {'Cash','Bank','General','Phone'} and data and data.company==company and data.account_type in {'Cash','Bank'} and (mode.type not in {'Cash','Bank'} or data.account_type==mode.type) and not data.is_group and not data.disabled and data.account_currency==currency==company_currency)
  methods.append({'mode_of_payment':mode.name,'type':data.account_type if valid else mode.type,'account':account if valid else None,'configured':valid,
   'reason':None if valid else 'Configure an enabled company Cash or Bank receiving account in the invoice currency.'})
 return methods


def _bank_reference(reference_no,reference_date):
 reference=str(reference_no or '').strip()
 if not reference or len(reference)>140 or any(ord(c)<32 for c in reference):
  frappe.throw('Enter the bank transfer reference number (up to 140 characters).')
 try:
  if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(reference_date or '')):raise ValueError
  date=getdate(reference_date)
  if date>getdate(nowdate()):raise ValueError
 except (ValueError,TypeError):frappe.throw('Enter a valid transfer date, no later than today (YYYY-MM-DD).')
 return reference,str(date)


@frappe.whitelist()
def get_collection_options(name):
 order=frappe.get_doc('WOB Delivery Order',name)
 if not own_driver(order.assigned_driver):
  frappe.throw('Only the active assigned driver can view collection methods.',frappe.PermissionError)
 order.check_permission('read')
 modes=frappe.get_all('Mode of Payment',filters={'enabled':1},fields=['name','type'],order_by='name asc')
 methods=[row for row in collection_methods(order.company,order.currency,modes) if row['configured']]
 allowed=allowed_payment_modes(order)
 if allowed is not None:methods=[row for row in methods if row['mode_of_payment'] in allowed]
 return {'methods':methods,'today':nowdate(),'bank_unavailable_reason':None if any(row['type']=='Bank' for row in methods) else 'Bank transfers need a valid company Bank account mapped in Mode of Payment. Contact Accounts.'}


def _submit_receipt(invoice,amount,account,order_name,request_id,collector,mode_of_payment='Cash',reference_no=None,reference_date=None):
 from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
 with _accounting_service():
  payment=get_payment_entry('Sales Invoice',invoice.name,bank_account=account)
  if payment.paid_from_account_currency!=invoice.currency or payment.paid_to_account_currency!=invoice.currency:
   frappe.throw('Mobile collection requires invoice and receivable accounts in the company currency.')
  payment.mode_of_payment=mode_of_payment
  if reference_no:
   payment.reference_no=reference_no
   payment.reference_date=reference_date
  payment.posting_date=nowdate()
  payment.custom_wob_delivery_order=order_name
  payment.custom_wob_collection_request=request_id
  payment.custom_wob_collected_by=collector
  payment.paid_amount=float(amount)
  payment.received_amount=float(amount)
  # Record exactly what the driver confirmed, with no write-offs or discounts.
  payment.set('deductions',[])
  remaining=amount
  for reference in payment.references:
   allocation=min(Decimal(str(reference.outstanding_amount)),remaining)
   reference.allocated_amount=float(allocation)
   remaining-=allocation
  if remaining:frappe.throw('Unable to allocate the collection to the linked invoice.')
  payment.remarks=f'{mode_of_payment} receipt confirmed by {collector} for delivery {order_name}.'
  payment.insert()
  payment.submit()
  return payment.name


def payment_summaries(orders):
 """Only call after checking access to every delivery in orders."""
 if not orders:return {}
 names=[order.get('name') for order in orders]
 invoice_names=list({order.get('sales_invoice') for order in orders if order.get('sales_invoice')})
 invoices={row.name:row for row in frappe.get_all('Sales Invoice',filters={'name':['in',invoice_names]},
  fields=['name','company','customer','currency','outstanding_amount','status','docstatus'])} if invoice_names else {}
 receipts=frappe.get_all('Payment Entry',filters={'custom_wob_delivery_order':['in',names],'docstatus':1},
  fields=['name','custom_wob_delivery_order','paid_amount','posting_date','custom_wob_collected_by','creation','mode_of_payment','reference_no','reference_date'],order_by='creation desc')
 result={}
 for order in orders:
  raw_invoice=invoices.get(order.get('sales_invoice'))
  is_valid=bool(raw_invoice and raw_invoice.company==order.get('company') and raw_invoice.customer==order.get('customer') and raw_invoice.docstatus==1)
  invoice=raw_invoice if is_valid else None
  rows=[row for row in receipts if row.custom_wob_delivery_order==order.get('name')]
  collected=sum(float(row.paid_amount) for row in rows)
  balance=max(0,float(invoice.outstanding_amount)) if invoice else (0.0 if (raw_invoice and raw_invoice.docstatus==2) else float(order.get('amount_to_collect') or 0))
  inv_status=raw_invoice.status if raw_invoice else None
  if raw_invoice and raw_invoice.docstatus==2:
   cash_status='Invoice Cancelled'
  elif rows and balance==0:
   cash_status='Collected'
  elif rows:
   cash_status='Partially Collected'
  elif balance:
   cash_status='Pending'
  else:
   cash_status='Not Applicable'
  result[order.get('name')]={
   'invoice_outstanding':balance if invoice else None,
   'invoice_status':inv_status,
   'collected_amount':collected,
   'payment_entry':rows[0].name if rows else None,
   'last_payment_method':rows[0].get('mode_of_payment') if rows else None,
   'last_payment_reference':rows[0].get('reference_no') if rows else None,
   'cash_status':cash_status,
   'collection_receipts':[dict(row) for row in rows],
  }
 return result


def payment_summary(order):
 return payment_summaries([order])[order.get('name')]


@frappe.whitelist(methods=['POST'])
def collect_payment(name,amount,request_id,expected_outstanding,mode_of_payment='Cash',reference_no=None,reference_date=None):
 if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9-]{16,100}',request_id):
  frappe.throw('A valid collection request ID is required.')
 lock_record('WOB Delivery Order',name)
 order=frappe.get_doc('WOB Delivery Order',name)
 if not own_driver(order.assigned_driver):
  frappe.throw('Only the active assigned driver can record this collection.',frappe.PermissionError)
 order.check_permission('read')
 if order.docstatus==2:frappe.throw('Canceled deliveries cannot receive payments.')
 if order.delivery_status not in {'Out for Delivery','Delivered'} or order.payment_type not in {'Cash on Delivery','Bank Transfer'}:
  frappe.throw('Payment can only be collected for an out-for-delivery or delivered Cash on Delivery order.')
 allowed=allowed_payment_modes(order)
 if allowed is not None and mode_of_payment not in allowed:
  frappe.throw('Use the Payment Mode selected on this Delivery Order.')
 existing=frappe.db.get_value('Payment Entry',{'custom_wob_collection_request':request_id},
  ['name','docstatus','custom_wob_delivery_order','paid_amount','mode_of_payment','reference_no','reference_date'],as_dict=True)
 if existing:
  if (existing.get('mode_of_payment') or 'Cash')!=mode_of_payment or ((existing.get('reference_no') or reference_no) and (str(existing.get('reference_no') or '')!=str(reference_no or '').strip() or str(existing.get('reference_date') or '')!=str(reference_date or ''))):
   frappe.throw('This request was already used with different payment details. Refresh before recording another receipt.')
  if existing.docstatus!=1 or existing.custom_wob_delivery_order!=name or Decimal(str(existing.paid_amount))!=validated_amount(amount,existing.paid_amount,9):
   frappe.throw('This collection request was already used or canceled. Refresh before recording another receipt.')
  return {**payment_summary(order),'payment_entry':existing.name}
 if not order.sales_invoice:frappe.throw('Link a submitted Sales Invoice before recording payment.')
 lock_record('Sales Invoice',order.sales_invoice)
 invoice=frappe.get_doc('Sales Invoice',order.sales_invoice)
 if invoice.docstatus!=1 or invoice.company!=order.company or invoice.customer!=order.customer or invoice.is_return:
  frappe.throw('The linked invoice is not valid for this collection.',frappe.PermissionError)
 precision=invoice.precision('outstanding_amount')
 if precision is None:precision=2
 value=validated_amount(amount,invoice.outstanding_amount,precision)
 try: expected=Decimal(str(expected_outstanding))
 except InvalidOperation:frappe.throw('Refresh the invoice balance before confirming payment.')
 if not expected.is_finite() or expected!=Decimal(str(invoice.outstanding_amount)):
  frappe.throw('The invoice balance has changed. Refresh before confirming payment.')
 account,kind=_collection_account(order.company,invoice.currency,mode_of_payment)
 if kind=='Bank':reference_no,reference_date=_bank_reference(reference_no,reference_date)
 else:reference_no=reference_date=None
 payment=_submit_receipt(invoice,value,account,name,request_id,frappe.session.user,mode_of_payment,reference_no,reference_date)
 # Payment Entry submission updates the invoice and GL in this same transaction.
 summary=payment_summary(order)
 frappe.publish_realtime('wob_delivery_update',{'name':name,'new_assignment':False},user=frappe.session.user,after_commit=True)
 return {**summary,'payment_entry':payment}
