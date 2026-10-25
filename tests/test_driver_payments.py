import unittest
from decimal import Decimal
from unittest.mock import Mock, patch
from types import SimpleNamespace
import frappe
from wob_delivery import payments

class DriverPaymentTests(unittest.TestCase):
 def test_amount_validation_rejects_invalid_overpayment_and_precision(self):
  for value in ['0','-1','NaN','Infinity','100.001','101','bad']:
   with self.subTest(value=value),patch.object(frappe,'throw',side_effect=ValueError):
    with self.assertRaises(ValueError):payments.validated_amount(value,100,2)
  self.assertEqual(payments.validated_amount('25.50',100,2),Decimal('25.50'))
 def test_foreign_driver_cannot_post_payment(self):
  order=SimpleNamespace(assigned_driver='OTHER')
  with patch.object(payments,'lock_record'),patch.object(frappe,'get_doc',return_value=order),patch.object(payments,'own_driver',return_value=False),patch.object(frappe,'throw',side_effect=PermissionError),patch.object(payments,'_submit_receipt') as submit:
   with self.assertRaises(PermissionError):payments.collect_payment('DEL-1','10','request-12345678','100')
   submit.assert_not_called()
 def test_duplicate_request_returns_receipt_without_posting_again(self):
  order=frappe._dict(name='DEL-1',assigned_driver='D1',delivery_status='Delivered',payment_type='Cash on Delivery',check_permission=Mock())
  existing=frappe._dict(name='PE-1',docstatus=1,custom_wob_delivery_order='DEL-1',paid_amount=10)
  with patch.object(payments,'lock_record'),patch.object(frappe,'get_doc',return_value=order),patch.object(payments,'own_driver',return_value=True),patch.object(frappe,'db',SimpleNamespace(get_value=lambda *a,**k:existing)),patch.object(payments,'payment_summary',return_value={'collected_amount':10}),patch.object(payments,'_submit_receipt') as submit:
   result=payments.collect_payment('DEL-1','10','request-12345678','100')
   self.assertEqual(result['payment_entry'],'PE-1');submit.assert_not_called()
 def test_same_request_cannot_be_reused_for_different_amount(self):
  order=frappe._dict(name='DEL-1',assigned_driver='D1',delivery_status='Delivered',payment_type='Cash on Delivery',check_permission=Mock())
  existing=frappe._dict(name='PE-1',docstatus=1,custom_wob_delivery_order='DEL-1',paid_amount=10)
  with patch.object(payments,'lock_record'),patch.object(frappe,'get_doc',return_value=order),patch.object(payments,'own_driver',return_value=True),patch.object(frappe,'db',SimpleNamespace(get_value=lambda *a,**k:existing)),patch.object(frappe,'throw',side_effect=ValueError):
   with self.assertRaises(ValueError):payments.collect_payment('DEL-1','20','request-12345678','100')
 def test_service_context_restores_driver_and_session_on_failure(self):
  session=SimpleNamespace(user='driver@example.com',sid='original-sid')
  local=SimpleNamespace(user_perms='driver-perms',role_permissions={'old':1},new_doc_templates={})
  with patch.object(frappe,'session',session),patch.object(frappe,'local',local):
   with self.assertRaises(RuntimeError):
    with payments._accounting_service():
     self.assertEqual(session.user,'Administrator')
     raise RuntimeError('posting rejected')
   self.assertEqual(session.user,'driver@example.com')
   self.assertEqual(session.sid,'original-sid')
   self.assertEqual(local.user_perms,'driver-perms')
 def test_delivered_read_access_remains_limited_to_own_assignment(self):
  from wob_delivery.domain import may_access
  self.assertTrue(may_access('Driver','A',set(),True,'Delivered'))
  self.assertFalse(may_access('Driver','A',{'A'},False,'Delivered'))
 def test_changed_invoice_balance_blocks_new_receipt(self):
  order=frappe._dict(name='DEL-1',assigned_driver='D1',delivery_status='Delivered',payment_type='Cash on Delivery',sales_invoice='INV-1',company='A',customer='C',check_permission=Mock())
  invoice=frappe._dict(name='INV-1',company='A',customer='C',docstatus=1,is_return=0,outstanding_amount=100,precision=lambda field:2)
  with patch.object(payments,'lock_record'),patch.object(frappe,'get_doc',side_effect=[order,invoice]),patch.object(payments,'own_driver',return_value=True),patch.object(frappe,'db',SimpleNamespace(get_value=lambda *a,**k:None)),patch.object(frappe,'throw',side_effect=ValueError),patch.object(payments,'_submit_receipt') as submit:
   with self.assertRaises(ValueError):payments.collect_payment('DEL-1','50','request-12345678','120')
   submit.assert_not_called()
 def test_canceled_receipt_cannot_be_recreated_by_retry(self):
  order=frappe._dict(name='DEL-1',assigned_driver='D1',delivery_status='Delivered',payment_type='Cash on Delivery',check_permission=Mock())
  existing=frappe._dict(name='PE-1',docstatus=2,custom_wob_delivery_order='DEL-1',paid_amount=10)
  with patch.object(payments,'lock_record'),patch.object(frappe,'get_doc',return_value=order),patch.object(payments,'own_driver',return_value=True),patch.object(frappe,'db',SimpleNamespace(get_value=lambda *a,**k:existing)),patch.object(frappe,'throw',side_effect=ValueError),patch.object(payments,'_submit_receipt') as submit:
   with self.assertRaises(ValueError):payments.collect_payment('DEL-1','10','request-12345678','100')
   submit.assert_not_called()
 def test_payment_summaries_gracefully_handles_cancelled_or_mismatched_invoice(self):
  order=frappe._dict(name='DEL-1',company='A',customer='C',sales_invoice='INV-CANCELLED',amount_to_collect=100)
  invoice=frappe._dict(name='INV-CANCELLED',company='A',customer='C',docstatus=2,status='Cancelled',outstanding_amount=100)
  with patch.object(frappe,'get_all',side_effect=[[invoice],[]]):
   summaries=payments.payment_summaries([order])
   self.assertIn('DEL-1',summaries)
   self.assertEqual(summaries['DEL-1']['cash_status'],'Invoice Cancelled')
   self.assertEqual(summaries['DEL-1']['invoice_status'],'Cancelled')


class DriverBankPaymentTests(unittest.TestCase):
 def test_bank_mode_cannot_post_to_cash_account(self):
  cash=frappe._dict(company='A',account_type='Cash',account_currency='QAR',is_group=0,disabled=0)
  with patch.object(frappe,'db',SimpleNamespace(get_value=Mock(side_effect=['Bank','Cash - A',cash]))),patch.object(frappe,'throw',side_effect=ValueError):
   with self.assertRaises(ValueError):payments._collection_account('A','QAR','Bank Transfer')
 def test_valid_bank_mapping_is_company_scoped(self):
  bank=frappe._dict(company='A',account_type='Bank',account_currency='QAR',is_group=0,disabled=0)
  lookup=Mock(side_effect=['Bank','Bank - A',bank,'QAR'])
  with patch.object(frappe,'db',SimpleNamespace(get_value=lookup)):
   self.assertEqual(payments._collection_account('A','QAR','Bank Transfer'),('Bank - A','Bank'))
   self.assertEqual(lookup.call_args_list[1].args[1],{'parent':'Bank Transfer','company':'A'})
 def test_bank_reference_and_date_are_required_and_not_future(self):
  with patch.object(payments,'nowdate',return_value='2026-10-25'),patch.object(frappe,'throw',side_effect=ValueError):
   for reference,date in [('', '2026-10-25'),('REF',''),('REF','invalid'),('REF','2026-10-26')]:
    with self.subTest(reference=reference,date=date),self.assertRaises(ValueError):payments._bank_reference(reference,date)
   self.assertEqual(payments._bank_reference(' REF-123 ','2026-10-24'),('REF-123','2026-10-24'))
 def test_retry_cannot_change_payment_method_or_reference(self):
  order=frappe._dict(name='DEL-1',assigned_driver='D1',delivery_status='Delivered',payment_type='Cash on Delivery',check_permission=Mock())
  existing=frappe._dict(name='PE-1',docstatus=1,custom_wob_delivery_order='DEL-1',paid_amount=10,mode_of_payment='Cash')
  with patch.object(payments,'lock_record'),patch.object(frappe,'get_doc',return_value=order),patch.object(payments,'own_driver',return_value=True),patch.object(frappe,'db',SimpleNamespace(get_value=lambda *a,**k:existing)),patch.object(frappe,'throw',side_effect=ValueError):
   with self.assertRaises(ValueError):payments.collect_payment('DEL-1','10','request-12345678','100',mode_of_payment='Bank Transfer',reference_no='REF',reference_date='2026-10-24')

class DeliveryBankSelectionTests(unittest.TestCase):
 def test_unpaid_bank_transfer_keeps_real_balance(self):
  from wob_delivery.domain import amount_to_collect
  self.assertEqual(amount_to_collect('Sales Invoice',450,450,'Bank Transfer'),450)
 def test_selected_bank_cannot_be_replaced_by_cash(self):
  order=frappe._dict(name='D',assigned_driver='DR',delivery_status='Delivered',payment_type='Bank Transfer',payment_mode='CBQ',check_permission=Mock())
  with patch.object(payments,'lock_record'),patch.object(payments,'own_driver',return_value=True),patch.object(frappe,'get_doc',return_value=order),patch.object(frappe,'throw',side_effect=ValueError):
   with self.assertRaises(ValueError):payments.collect_payment('D',10,'request-12345678',450,mode_of_payment='Cash')

class AllowedPaymentModesTests(unittest.TestCase):
 def test_checked_modes_are_unique_and_legacy_single_mode_is_preserved(self):
  self.assertEqual(payments.allowed_payment_modes(frappe._dict(allowed_payment_modes='["Cash","CBQ","Cash"]')),['Cash','CBQ'])
  self.assertEqual(payments.allowed_payment_modes(frappe._dict(payment_mode='CBQ')),['CBQ'])
 def test_malformed_checkbox_payload_is_rejected(self):
  with patch.object(frappe,'throw',side_effect=ValueError):
   for raw in ['{}','[1]','invalid']:
    with self.subTest(raw=raw),self.assertRaises(ValueError):payments.allowed_payment_modes(frappe._dict(allowed_payment_modes=raw))
 def test_explicit_empty_selection_is_distinct_from_legacy(self):
  self.assertEqual(payments.allowed_payment_modes(frappe._dict(allowed_payment_modes='[]',payment_mode='Cash')),[])
