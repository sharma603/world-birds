import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import frappe
from wob_delivery import api

class EligibleCompaniesTests(unittest.TestCase):
 def test_without_company_limits_search_and_uses_source_company(self):
  row={'name':'SO-1','company':'Company A'}
  source=Mock(company='Company A');source.get.return_value=False
  with patch.object(api,'companies',return_value={'Company A'},create=True), patch.object(api,'role_kind',return_value='Manager'), patch.object(api,'assert_company') as check, patch.object(frappe,'get_list',return_value=[SimpleNamespace(**row)]) as listing, patch.object(frappe,'get_doc',return_value=source), patch.object(api,'fulfillment_key',return_value='key') as key, patch.object(frappe,'db',SimpleNamespace(exists=lambda *a:False)):
   self.assertEqual(len(api.get_eligible_orders(source_type='Sales Order')),1)
   self.assertEqual(listing.call_args.kwargs['filters']['company'],['in',['Company A']])
   self.assertIn('company',listing.call_args.kwargs['fields'])
   check.assert_called_once_with('Company A')
   self.assertEqual(key.call_args.args[0],'Company A')
 def test_no_allowed_companies_returns_no_documents(self):
  with patch.object(api,'companies',return_value=set(),create=True),patch.object(api,'role_kind',return_value='Manager'),patch.object(frappe,'get_list') as listing:
   self.assertEqual(api.get_eligible_orders(),[])
   listing.assert_not_called()
 def test_selected_company_still_checked(self):
  with patch.object(api,'assert_company',side_effect=PermissionError):
   with self.assertRaises(PermissionError):api.get_eligible_orders('Forbidden')
 def test_delivered_task_is_not_offered_again(self):
  row=SimpleNamespace(name='SO-1',company='Company A')
  source=Mock(company='Company A');source.get.return_value=False
  def exists(doctype,filters):
   return filters.get('sales_order')=='SO-1' and filters.get('delivery_status')=='Delivered'
  with patch.object(api,'assert_company'),patch.object(frappe,'get_list',return_value=[row]),patch.object(frappe,'get_doc',return_value=source),patch.object(api,'fulfillment_key',return_value='key'),patch.object(frappe,'db',SimpleNamespace(exists=exists)):
   self.assertEqual(api.get_eligible_orders('Company A','Sales Order'),[])
 def test_fully_delivered_sales_orders_are_filtered(self):
  with patch.object(api,'assert_company'),patch.object(frappe,'get_list',return_value=[]) as listing:
   api.get_eligible_orders('Company A','Sales Order')
   self.assertEqual(listing.call_args.kwargs['filters']['per_delivered'],['<',100])
