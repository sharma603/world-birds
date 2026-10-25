import unittest
from unittest.mock import Mock, patch
from wob_delivery import mobile
import frappe

class MobileStatusTests(unittest.TestCase):
 def setup_patches(self,owned=True,status='Out for Delivery'):
  doc=Mock(name='DEL-1',assigned_driver='DRIVER-1',delivery_status=status)
  doc.as_dict.return_value={'name':'DEL-1','delivery_status':'Delivered'}
  return doc,patch.multiple(mobile,now_datetime=Mock(return_value="2026-10-24 10:00:00"),lock_record=Mock(),own_driver=Mock(return_value=owned),record_history=Mock(),sync_sales_order_status=Mock(),publish_delivery_update=Mock())
 def test_completion_uses_own_assignment_without_sales_document_access(self):
  doc,patches=self.setup_patches()
  with patches,patch.object(frappe,'get_doc',return_value=doc),patch.object(frappe,'throw',side_effect=PermissionError):
   mobile.update_delivery_status('DEL-1','Delivered')
   doc.check_permission.assert_called_once_with('read')
   self.assertEqual(doc.db_set.call_args.args[0]['delivery_status'],'Delivered')
   self.assertIsNone(doc.db_set.call_args.args[0]['active_fulfillment_key'])
   mobile.record_history.assert_called_once_with(doc)
   mobile.sync_sales_order_status.assert_called_once_with(doc)
   mobile.publish_delivery_update.assert_called_once_with(doc)
   doc.save.assert_not_called()
 def test_other_drivers_delivery_is_rejected(self):
  doc,patches=self.setup_patches(owned=False)
  with patches,patch.object(frappe,'get_doc',return_value=doc),patch.object(frappe,'throw',side_effect=PermissionError):
   with self.assertRaises(PermissionError):mobile.update_delivery_status('DEL-1','Delivered')
   doc.db_set.assert_not_called()
 def test_cannot_skip_dispatch_or_cancel_delivery(self):
  for target in ['Delivered','Cancelled']:
   doc,patches=self.setup_patches(status='Assigned')
   with patches,patch.object(frappe,'get_doc',return_value=doc),patch.object(frappe,'throw',side_effect=ValueError):
    with self.assertRaises(ValueError):mobile.update_delivery_status('DEL-1',target)
    doc.db_set.assert_not_called()
