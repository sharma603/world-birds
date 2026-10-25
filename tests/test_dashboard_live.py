import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
import frappe
from wob_delivery import live

class DashboardLiveTests(unittest.TestCase):
 def test_insert_flag_wins_over_history_db_set_before_save_snapshot(self):
  doc=SimpleNamespace(flags={'in_insert':True},get_doc_before_save=lambda:frappe._dict(delivery_status='Pending'))
  self.assertEqual(live.classify_change(doc),'created')
 def test_event_contains_only_safe_fields_and_targets_explicit_users_after_commit(self):
  doc=frappe._dict(name='DEL-1',company='A',modified='2026-10-24 12:00:00',customer='Private customer',amount_to_collect=999)
  with patch.object(live,'dashboard_recipients',return_value=['allowed@example.com']),patch.object(frappe,'publish_realtime') as publish:
   live.publish_dashboard_change(doc,'updated')
   args=publish.call_args
   self.assertEqual(args.args[0],'wob_delivery_changed')
   self.assertEqual(args.kwargs,{'user':'allowed@example.com','after_commit':True})
   self.assertEqual(set(args.args[1]),{'delivery_id','company','action','revision','event_id'})
 def test_staff_company_scope_and_record_permissions_both_apply(self):
  roles=[frappe._dict(parent='A-user',role='WOB Delivery Dispatcher'),frappe._dict(parent='B-user',role='WOB Delivery Manager'),frappe._dict(parent='record-denied',role='WOB Delivery Manager'),frappe._dict(parent='disabled',role='System Manager')]
  def get_all(dt,**kw):
   if dt=='Has Role':return roles
   if dt=='User':return ['Administrator','A-user','B-user','record-denied']
   return [frappe._dict(user='A-user'),frappe._dict(user='record-denied')]
  with patch.object(frappe,'get_all',side_effect=get_all),patch.object(frappe,'has_permission',side_effect=lambda *a,**k:k['user']!='record-denied'):
   self.assertEqual(live.dashboard_recipients(frappe._dict(company='A')),['A-user','Administrator'])
 def test_status_and_reassignment_actions_use_actual_before_save_state(self):
  doc=SimpleNamespace(assigned_driver='D2',delivery_status='Assigned',get_doc_before_save=lambda:SimpleNamespace(assigned_driver='D1',delivery_status='Assigned'))
  self.assertEqual(live.classify_change(doc),'reassigned')
  doc.get_doc_before_save=lambda:SimpleNamespace(assigned_driver='D2',delivery_status='Assigned')
  doc.delivery_status='Delivered'
  self.assertEqual(live.classify_change(doc),'delivered')
 def test_no_recipients_never_broadcasts_site_wide(self):
  with patch.object(live,'dashboard_recipients',return_value=[]),patch.object(frappe,'publish_realtime') as publish:
   live.publish_dashboard_change(frappe._dict(name='DEL-1',company='A'),'deleted')
   publish.assert_not_called()
