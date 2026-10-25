import frappe
from wob_delivery.domain import ACTIVE, may_access

STAFF = {'WOB Delivery Manager', 'WOB Delivery Dispatcher'}

def role_kind(user=None):
 user = user or frappe.session.user
 if user == 'Guest': return None
 roles = set(frappe.get_roles(user))
 if user == 'Administrator' or roles.intersection({'System Manager', 'WOB Delivery Administrator'}): return 'Administrator'
 if roles.intersection(STAFF): return 'Manager'
 if 'WOB Delivery Driver' in roles: return 'Driver'
 return None

def companies(user=None):
 user = user or frappe.session.user
 if role_kind(user) == 'Administrator': return set(frappe.get_all('Company', pluck='name'))
 permissions = frappe.permissions.get_user_permissions(user).get('Company', [])
 return {x.doc for x in permissions}

def assert_company(company, user=None, manager=False):
 user = user or frappe.session.user
 if role_kind(user) not in {'Administrator','Manager'} or company not in companies(user):
  frappe.throw('You are not authorized to manage deliveries for this company.', frappe.PermissionError)
 if manager and role_kind(user) != 'Administrator' and 'WOB Delivery Manager' not in frappe.get_roles(user):
  frappe.throw('A delivery manager is required for this action.', frappe.PermissionError)

def own_driver(driver, user=None):
 if not driver: return False
 data=frappe.db.get_value('Driver',driver,['user','status'],as_dict=True)
 return bool(data and data.user == (user or frappe.session.user) and data.status == 'Active' and frappe.db.get_value('User',data.user,'enabled'))

def order_permission(doc, user=None, permission_type=None, **kwargs):
 user=user or frappe.session.user
 kind=role_kind(user)
 if doc and doc.get('delivery_status')=='Delivered':
  if permission_type == 'delete':
   if kind not in {'Administrator','Manager'}: return False
  elif permission_type in {'write','create','cancel','amend'}:
   return False
 if not doc or not doc.get('company'): return kind in {'Administrator','Manager'}
 if kind=='Driver' and permission_type not in {None,'read','select','print'}: return False
 return may_access(kind,doc.company,companies(user),own_driver(doc.get('assigned_driver'),user),doc.get('delivery_status'))

def staff_permission(doc, user=None, permission_type=None, **kwargs):
 user=user or frappe.session.user
 if role_kind(user) not in {'Administrator','Manager'}: return False
 return not doc or not doc.get('company') or doc.company in companies(user)

def order_query(user=None):
 user=user or frappe.session.user
 kind=role_kind(user)
 if kind=='Driver':
  statuses=', '.join(frappe.db.escape(x) for x in sorted(ACTIVE | {'Delivered'}))
  return f"`tabWOB Delivery Order`.delivery_status in ({statuses}) AND EXISTS (SELECT 1 FROM `tabDriver` d JOIN `tabUser` u ON u.name=d.user WHERE d.name=`tabWOB Delivery Order`.assigned_driver AND d.user={frappe.db.escape(user)} AND d.status='Active' AND u.enabled=1)"
 return company_query('WOB Delivery Order',user)

def company_query(doctype,user=None):
 user=user or frappe.session.user
 if role_kind(user)=='Administrator': return ''
 if role_kind(user)!='Manager': return '1=0'
 allowed=companies(user)
 if not allowed:return '1=0'
 return f'`tab{doctype}`.company IN ('+', '.join(frappe.db.escape(x) for x in sorted(allowed))+')'

def zone_query(user=None): return company_query('WOB Delivery Zone',user)
def assignment_query(user=None): return company_query('WOB Driver Zone Assignment',user)
def history_query(user=None): return company_query('WOB Delivery Assignment History',user)
