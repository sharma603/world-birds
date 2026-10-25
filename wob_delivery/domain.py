"""Delivery-only rules; ERPNext remains authoritative for money and stock."""
from decimal import Decimal

STATUSES = ('Pending', 'Ready for Dispatch', 'Assigned', 'Out for Delivery', 'Delivered', 'Failed', 'Rescheduled', 'Cancelled')
TERMINAL = {'Delivered', 'Cancelled'}
ACTIVE = set(STATUSES) - TERMINAL
TRANSITIONS = {
 'Pending': {'Ready for Dispatch', 'Cancelled'},
 'Ready for Dispatch': {'Assigned', 'Pending', 'Cancelled'},
 'Assigned': {'Out for Delivery', 'Ready for Dispatch', 'Rescheduled', 'Cancelled'},
 'Out for Delivery': {'Delivered', 'Failed', 'Rescheduled'},
 'Failed': {'Rescheduled', 'Ready for Dispatch', 'Cancelled'},
 'Rescheduled': {'Ready for Dispatch', 'Assigned', 'Cancelled'},
}

def check_transition(previous, current, manager=False, reason=''):
 if previous not in STATUSES or current not in STATUSES:
  raise ValueError('Unknown delivery status.')
 if previous == current:
  return
 if previous=='Delivered':
  raise ValueError('Delivered orders are locked and cannot be reopened.')
 if previous in TERMINAL:
  if not manager or not str(reason or '').strip():
   raise ValueError('Reopening a cancelled delivery requires a delivery manager and an override reason.')
  return
 if current not in TRANSITIONS.get(previous, set()):
  raise ValueError(f'Cannot change delivery status from {previous} to {current}.')

def amount_to_collect(source_type, total, paid_or_outstanding, payment_type):
 total = Decimal(str(total or 0))
 value = Decimal(str(paid_or_outstanding or 0))
 if total < 0:
  raise ValueError('Return documents cannot be used for delivery collection.')
 balance = value if source_type == 'Sales Invoice' else total - value
 balance = max(Decimal('0'), balance)
 if payment_type == 'Prepaid':
  if balance > 0:
   raise ValueError('The source document has an unpaid balance. Use Cash on Delivery/Other or record payment in ERPNext first.')
  return 0.0
 return float(balance)

def may_access(role, company, companies, own_assignment, status):
 if role == 'Administrator':
  return True
 if role == 'Manager':
  return company in companies
 return role == 'Driver' and own_assignment and status in (ACTIVE | {'Delivered'})
