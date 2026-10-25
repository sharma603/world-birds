import unittest
from unittest.mock import patch,Mock
import frappe
from wob_delivery import bank_setup

class BankSetupTests(unittest.TestCase):
 def test_driver_cannot_configure_banks(self):
  with patch.object(bank_setup,'role_kind',return_value='Driver'),patch.object(frappe,'throw',side_effect=PermissionError),patch.object(frappe,'get_doc') as read:
   with self.assertRaises(PermissionError):bank_setup.save_bank_collection('A','QNB',account='Bank - A')
   read.assert_not_called()
 def test_cash_account_is_rejected_before_any_save(self):
  account=frappe._dict(company='A',account_type='Cash',is_group=0,disabled=0,account_currency='QAR',check_permission=Mock())
  with patch.object(bank_setup,'role_kind',return_value='Administrator'),patch.object(bank_setup,'assert_company'),patch.object(frappe,'get_doc',return_value=account),patch.object(frappe,'has_permission',return_value=True),patch.object(frappe,'db',Mock(get_value=Mock(return_value='QAR'))),patch.object(frappe,'throw',side_effect=ValueError):
   with self.assertRaises(ValueError):bank_setup.save_bank_collection('A','QNB',account='Cash - A')
 def test_existing_cash_payment_mode_cannot_be_converted_to_bank(self):
  account=frappe._dict(company='A',account_type='Bank',is_group=0,disabled=0,account_currency='QAR',check_permission=Mock())
  mode=frappe._dict(type='Cash',check_permission=Mock())
  with patch.object(bank_setup,'role_kind',return_value='Administrator'),patch.object(bank_setup,'assert_company'),patch.object(frappe,'get_doc',side_effect=[account,mode]),patch.object(frappe,'has_permission',return_value=True),patch.object(frappe,'db',Mock(get_value=Mock(return_value='QAR'),exists=Mock(return_value=True))),patch.object(frappe,'throw',side_effect=ValueError):
   with self.assertRaises(ValueError):bank_setup.save_bank_collection('A','Cash',account='Bank - A')
