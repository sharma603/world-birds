"""Admin setup of driver collection banks using standard ERPNext accounting masters."""
import frappe
from wob_delivery.permissions import role_kind, assert_company


@frappe.whitelist(methods=['POST'])
def save_bank_collection(company,bank_name,account=None,parent_account=None):
 if role_kind()!='Administrator':
  frappe.throw('Only a delivery administrator can configure bank collection.',frappe.PermissionError)
 assert_company(company)
 bank_name=str(bank_name or '').strip()
 if not bank_name or len(bank_name)>100 or any(ord(c)<32 for c in bank_name):
  frappe.throw('Enter a bank/payment name of up to 100 characters.')
 currency=frappe.db.get_value('Company',company,'default_currency')
 # Check native accounting permissions before creating any master records.
 exists=frappe.db.exists('Mode of Payment',bank_name)
 if not frappe.has_permission('Mode of Payment',ptype='write' if exists else 'create'):
  frappe.throw('Accounting permission is required to configure bank payment methods.',frappe.PermissionError)
 if account:
  bank=frappe.get_doc('Account',account)
  bank.check_permission('read')
 else:
  if not parent_account:frappe.throw('Select the Bank account group for the new receiving account.')
  parent=frappe.get_doc('Account',parent_account)
  parent.check_permission('read')
  if parent.company!=company or not parent.is_group or parent.root_type!='Asset' or parent.disabled:
   frappe.throw('Select an enabled Asset account group belonging to this company.')
  bank=frappe.get_doc({'doctype':'Account','account_name':bank_name,'company':company,
   'parent_account':parent_account,'account_type':'Bank','account_currency':currency,'is_group':0})
  bank.insert()
 if bank.company!=company or bank.account_type!='Bank' or bank.is_group or bank.disabled or bank.account_currency!=currency:
  frappe.throw('Select an enabled company Bank ledger account in the company currency.')
 if exists:
  mode=frappe.get_doc('Mode of Payment',bank_name)
  mode.check_permission('write')
  if mode.type!='Bank':frappe.throw('This name is already used by a non-bank payment method. Choose a different bank name.')
 else:
  mode=frappe.get_doc({'doctype':'Mode of Payment','mode_of_payment':bank_name,'type':'Bank'})
 mode.enabled=1
 mapping=next((row for row in mode.accounts if row.company==company),None)
 if mapping:mapping.default_account=bank.name
 else:mode.append('accounts',{'company':company,'default_account':bank.name})
 mode.save()
 return {'mode_of_payment':mode.name,'account':bank.name,'company':company}


@frappe.whitelist()
def get_bank_account(company,bank):
 assert_company(company)
 from wob_delivery.payments import _collection_account
 currency=frappe.db.get_value('Company',company,'default_currency')
 account,kind=_collection_account(company,currency,bank)
 return {'account':account,'type':kind}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def payment_mode_query(doctype,txt,searchfield,start,page_len,filters):
 filters=frappe._dict(filters or {})
 assert_company(filters.company)
 currency=frappe.db.get_value('Company',filters.company,'default_currency')
 choices=[]
 modes=frappe.get_list('Mode of Payment',filters={'enabled':1,'type':['in',['Cash','Bank']],'name':['like','%'+txt+'%']},fields=['name','type'],order_by='name asc',limit_page_length=0)
 for mode in modes:
  # Validate mappings without exposing disabled or cross-company accounts.
  account=frappe.db.get_value('Mode of Payment Account',{'parent':mode.name,'company':filters.company},'default_account')
  if mode.type=='Cash':account=account or frappe.db.get_value('Company',filters.company,'default_cash_account')
  data=frappe.db.get_value('Account',account,['company','account_type','account_currency','is_group','disabled'],as_dict=True) if account else None
  if data and data.company==filters.company and data.account_type==mode.type and not data.is_group and not data.disabled and data.account_currency==currency:choices.append([mode.name,mode.type,account])
 return choices[int(start):int(start)+int(page_len)]


@frappe.whitelist()
def get_active_payment_methods(company):
 assert_company(company)
 from wob_delivery.payments import collection_methods
 currency=frappe.db.get_value('Company',company,'default_currency')
 modes=frappe.get_list('Mode of Payment',filters={'enabled':1},fields=['name','type'],order_by='name asc',limit_page_length=0)
 return collection_methods(company,currency,modes)
