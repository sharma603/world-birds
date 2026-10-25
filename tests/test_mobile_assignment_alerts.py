import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import frappe
from wob_delivery import mobile

class AssignmentAlertTests(unittest.TestCase):
 def doc(self,old=None,driver='D2',status='Assigned',**kwargs):
  d=SimpleNamespace(name='DEL-1',assigned_driver=driver,delivery_status=status,modified='2026-10-24 10:00:00',get_doc_before_save=lambda:old)
  for k,v in kwargs.items():setattr(d,k,v)
  return d
 def test_reassignment_targets_new_and_old_driver_after_commit(self):
  old=SimpleNamespace(assigned_driver='D1',delivery_status='Assigned')
  with patch.object(frappe,'db',SimpleNamespace(get_value=lambda dt,name,field: name+'@example.com')),patch.object(frappe,'publish_realtime') as publish:
   mobile.publish_delivery_update(self.doc(old))
   self.assertEqual(publish.call_count,2)
   sent={c.kwargs['user']:c for c in publish.call_args_list}
   self.assertTrue(sent['D2@example.com'].args[1]['new_assignment'])
   self.assertFalse(sent['D1@example.com'].args[1]['new_assignment'])
   self.assertTrue(all(c.kwargs['after_commit'] for c in sent.values()))
 def test_ordinary_save_does_not_ring(self):
  with patch.object(frappe,'publish_realtime') as publish:
   mobile.publish_delivery_update(self.doc(SimpleNamespace(assigned_driver='D2',delivery_status='Assigned')))
   publish.assert_not_called()
 def test_guest_cannot_read_mobile_context(self):
  with patch.object(mobile,'role_kind',return_value=None),patch.object(frappe,'throw',side_effect=PermissionError):
   with self.assertRaises(PermissionError):mobile.get_context()
 def test_status_change_refreshes_without_new_assignment_ring(self):
  old=SimpleNamespace(assigned_driver='D2',delivery_status='Assigned')
  with patch.object(frappe,'db',SimpleNamespace(get_value=lambda *a:'driver@example.com')),patch.object(frappe,'publish_realtime') as publish:
   mobile.publish_delivery_update(self.doc(old,status='Out for Delivery'))
   self.assertFalse(publish.call_args.args[1]['new_assignment'])
 def test_payment_methods_change_publishes_update_without_ringing(self):
  old=SimpleNamespace(assigned_driver='D2',delivery_status='Assigned',allowed_payment_modes='["Cash"]')
  with patch.object(frappe,'db',SimpleNamespace(get_value=lambda *a:'driver@example.com')),patch.object(frappe,'publish_realtime') as publish:
   mobile.publish_delivery_update(self.doc(old,allowed_payment_modes='["Cash","Bank Transfer"]'))
   publish.assert_called_once()
   self.assertFalse(publish.call_args.args[1]['new_assignment'])
   self.assertEqual(publish.call_args.kwargs['user'],'driver@example.com')
 def test_context_only_queries_current_users_driver(self):
  driver=frappe._dict(name='DRIVER-SELF')
  db=Mock();db.get_value.return_value=driver
  with patch.object(mobile,'role_kind',return_value='Driver'),patch.object(frappe,'db',db),patch.object(frappe,'session',SimpleNamespace(user='self@example.com')),patch.object(frappe,'local',SimpleNamespace(site='test.local')),patch.object(frappe,'conf',{}),patch.object(frappe,'get_list',return_value=[]) as listing:
   context=mobile.get_context()
   self.assertEqual(db.get_value.call_args.args[1],{'user':'self@example.com','status':'Active'})
   self.assertEqual(listing.call_args.kwargs['filters']['assigned_driver'],'DRIVER-SELF')
   self.assertEqual(context['site'],'test.local')
