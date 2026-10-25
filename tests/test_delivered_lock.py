import unittest
from unittest.mock import Mock,patch
import frappe
from wob_delivery import services,api

class DeliveredLockTests(unittest.TestCase):
 def test_delivered_order_cannot_be_saved_even_with_manager_override(self):
  doc=Mock(change_reason='Manager override',delivery_status='Delivered')
  with patch.object(frappe,'throw',side_effect=lambda message,*args: (_ for _ in ()).throw(ValueError(message))):
   with self.assertRaisesRegex(ValueError,'Delivered orders are locked'):services.assert_delivery_editable(doc)
 def test_delivered_order_cannot_be_relinked_by_fulfillment_actions(self):
  doc=Mock(company='A',delivery_status='Delivered')
  for method in (api.sync_fulfillment_documents,api.create_fulfillment_documents):
   with self.subTest(method=method.__name__),patch.object(api,'lock_record',create=True),patch.object(api,'assert_company'),patch.object(frappe,'get_doc',return_value=doc),patch.object(frappe,'db',Mock()),patch.object(frappe,'throw',side_effect=ValueError('Delivered orders are locked')):
    with self.assertRaisesRegex(ValueError,'Delivered orders are locked'):method('DEL-1')
    doc.db_set.assert_not_called()
