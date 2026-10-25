import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import frappe
from wob_delivery import mobile

class DeliveryItemTests(unittest.TestCase):
 def fixtures(self):
  order=Mock(company='Company A',customer='Customer A')
  order.get.side_effect=lambda field: {'delivery_note':'DN-1','sales_invoice':'INV-1','sales_order':'SO-1'}.get(field)
  order.as_dict.return_value={'name':'DEL-1','company':'Company A'}
  item=frappe._dict(name='ROW-1',item_code='ITEM-1',item_name='Bird feed',qty=3,uom='Bag',description='<p>Feed</p>',rate=100)
  source=SimpleNamespace(company='Company A',customer='Customer A',docstatus=1,items=[item])
  return order,source
 def test_delivery_note_items_are_projected_after_delivery_permission_check(self):
  order,source=self.fixtures()
  with patch.object(mobile,'payment_summary',return_value={}),patch.object(frappe,'get_doc',side_effect=[order,source]) as get_doc:
   result=mobile.get_delivery_details('DEL-1')
   order.check_permission.assert_called_once_with('read')
   self.assertEqual(get_doc.call_args.args,('Delivery Note','DN-1'))
   self.assertEqual(result['items'][0]['qty'],3)
   self.assertEqual(result['items'][0]['item_name'],'Bird feed')
   self.assertNotIn('rate',result['items'][0])
 def test_forbidden_delivery_does_not_read_source_items(self):
  order,_=self.fixtures();order.check_permission.side_effect=PermissionError
  with patch.object(frappe,'get_doc',return_value=order) as get_doc:
   with self.assertRaises(PermissionError):mobile.get_delivery_details('OTHER-DEL')
   self.assertEqual(get_doc.call_count,1)
 def test_cross_company_source_is_rejected(self):
  order,source=self.fixtures();source.company='Other Company'
  with patch.object(mobile,'payment_summary',return_value={}),patch.object(frappe,'get_doc',side_effect=[order,source]),patch.object(frappe,'throw',side_effect=PermissionError):
   with self.assertRaises(PermissionError):mobile.get_delivery_details('DEL-1')
