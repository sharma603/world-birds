import unittest
from unittest.mock import patch, Mock
import frappe
from wob_delivery import dashboard


class DashboardTests(unittest.TestCase):
 def test_pagination_is_capped_and_sort_is_allowlisted(self):
  self.assertEqual(dashboard.page_options(-1, 999, 'customer', 'DESC'), (1, 100, 'customer', 'desc'))
  with patch.object(frappe, 'throw', side_effect=ValueError), self.assertRaises(ValueError):
   dashboard.page_options(1, 25, 'name; drop table x', 'asc')

 def test_today_intersects_status_instead_of_replacing(self):
  filters = dashboard.intersect_filters({'delivery_status':'Failed'}, completed_today=1, issues_only=1, today='2026-10-24')
  self.assertIn(['delivery_status', '=', 'Failed'], filters)
  self.assertIn(['delivery_status', '=', 'Delivered'], filters)
  self.assertIn(['delivery_status', 'in', ['Failed', 'Rescheduled']], filters)

 def test_group_rows_merge_null_and_empty_driver(self):
  rows = [dict(assigned_driver=None, delivery_status='Pending', count=2, delivered_today=0), dict(assigned_driver='', delivery_status='Assigned', count=1, delivered_today=0)]
  result = dashboard.group_rows(rows, 'assigned_driver', {})
  self.assertEqual(len(result), 1)
  self.assertEqual(result[0]['label'], 'Unassigned')
  self.assertEqual(result[0]['active_count'], 3)

 def test_delivered_action_never_mutates_delivered_order(self):
  doc = Mock(company='A', delivery_status='Delivered')
  with patch.object(dashboard, 'assert_company'), patch.object(dashboard, 'lock_record'), patch.object(frappe, 'get_doc', return_value=doc), patch.object(frappe, 'throw', side_effect=ValueError):
   with self.assertRaises(ValueError): dashboard.perform_action('D1', 'failed')
  doc.save.assert_not_called()

 def test_scope_drives_every_aggregate_and_totals_exceed_page(self):
  from wob_delivery import api
  calls=[]
  def sql(statement, params, as_dict):
   calls.append((statement,dict(params)))
   if 'FROM `tabPayment Entry`' in statement: return [frappe._dict(total=12)]
   if 'FROM `tabSales Invoice`' in statement: return [frappe._dict(total=45)]
   if 'GROUP BY d.delivery_status' in statement: return [frappe._dict(delivery_status='Pending',count=1001,delivered_today=0)]
   return []
  scope=Mock();scope.walk.return_value=('SELECT name FROM permitted_deliveries',{'permission_user':'staff'})
  with patch.object(api,'delivery_filters',return_value={'company':'A'}), patch.object(frappe,'get_list',return_value=scope) as listing, patch.object(frappe,'db',new=Mock(sql=sql)), patch.object(dashboard,'nowdate',return_value='2026-10-24'), patch.object(dashboard,'now_datetime',return_value='2026-10-24 12:00:00'), patch.object(dashboard,'get_system_timezone',return_value='Asia/Qatar'), patch.object(dashboard,'role_kind',return_value='Manager'):
   result=dashboard.get_dashboard(customer_search="x' OR 1=1 --",page=2)
  self.assertEqual(result['pagination']['total'],1001)
  self.assertEqual(result['counts']['Pending'],1001)
  self.assertEqual(result['cash_collected_today'],12)
  self.assertTrue(listing.call_args.kwargs['run'] is False)
  self.assertTrue(all('SELECT name FROM permitted_deliveries' in statement for statement,_ in calls))
  self.assertTrue(all("x' OR 1=1" not in statement for statement,_ in calls))
  self.assertEqual(calls[1][1]['dash_offset'],25)

 def test_details_checks_read_before_history(self):
  doc=Mock();doc.check_permission.side_effect=PermissionError
  with patch.object(frappe,'get_doc',return_value=doc), patch.object(frappe,'get_all') as history:
   with self.assertRaises(PermissionError): dashboard.get_task_details('secret')
  history.assert_not_called()

 def test_recommendations_use_bulk_global_capacity_and_company_workload(self):
  from wob_delivery import api
  mapping=frappe._dict(driver='D1',driver_user='u',assignment_type='Primary',availability_status='Available',maximum_active_deliveries=3)
  driver=frappe._dict(name='D1',full_name='Ali',user='u',status='Active')
  rows=[frappe._dict(assigned_driver='D1',company='A',count=1),frappe._dict(assigned_driver='D1',company='B',count=2)]
  with patch.object(api,'assert_company'), patch.object(frappe,'get_doc',return_value=frappe._dict(company='A',active=1)), patch.object(frappe,'get_list',return_value=[mapping]), patch.object(frappe,'get_all',side_effect=[[driver],['u'],rows]) as bulk:
   result=api.get_driver_recommendations('A','Z')
  self.assertEqual(bulk.call_count,3)
  self.assertEqual(result[0]['active_deliveries'],1)
  self.assertFalse(result[0]['can_assign'])

 def test_empty_group_sentinels_are_null_filters_without_company_assertion(self):
  from wob_delivery import api
  with patch.object(api,'role_kind',return_value='Manager'), patch.object(api,'assert_company') as company:
   filters=api.delivery_filters(company='__unassigned__',delivery_zone='__unassigned__',driver='__unassigned__')
  company.assert_not_called()
  self.assertEqual(filters['assigned_driver'],['is','not set'])
  self.assertEqual(filters['delivery_zone'],['is','not set'])
  self.assertEqual(filters['company'],['is','not set'])

 def test_zone_group_uses_zone_title(self):
  rows=[dict(delivery_zone='ZONE-1',delivery_status='Pending',count=1)]
  self.assertEqual(dashboard.group_rows(rows,'delivery_zone',{'ZONE-1':'Doha'})[0]['label'],'Doha')

 def test_page_labels_are_loaded_in_bulk(self):
  from wob_delivery import api
  order=frappe._dict(name='D1',customer='C1',assigned_driver='DR1',delivery_zone='Z1')
  def sql(statement,params,as_dict):
   if 'FROM `tabPayment Entry`' in statement or 'FROM `tabSales Invoice`' in statement: return [frappe._dict(total=0)]
   if 'GROUP BY d.delivery_status' in statement: return [frappe._dict(delivery_status='Pending',count=1,delivered_today=0)]
   if 'GROUP BY d.`assigned_driver`' in statement: return [frappe._dict(assigned_driver='DR1',delivery_status='Pending',count=1)]
   if 'GROUP BY d.`delivery_zone`' in statement: return [frappe._dict(delivery_zone='Z1',delivery_status='Pending',count=1)]
   if 'LIMIT' in statement: return [order]
   return []
  scope=Mock();scope.walk.return_value=('SELECT name FROM permitted',{})
  bulk=[[frappe._dict(name='DR1',full_name='Ali')],[frappe._dict(name='Z1',zone_name='Doha')],[frappe._dict(name='C1',customer_name='Customer One')]]
  with patch.object(api,'delivery_filters',return_value={}), patch.object(frappe,'get_list',return_value=scope), patch.object(frappe,'get_all',side_effect=bulk) as lookup, patch.object(frappe,'db',new=Mock(sql=sql)), patch.object(dashboard,'nowdate',return_value='2026-10-24'), patch.object(dashboard,'now_datetime',return_value='2026-10-24 12:00:00'), patch.object(dashboard,'get_system_timezone',return_value='Asia/Qatar'), patch.object(dashboard,'role_kind',return_value='Manager'):
   result=dashboard.get_dashboard()
  self.assertEqual(lookup.call_count,3)
  self.assertEqual(result['orders'][0]['customer_name'],'Customer One')
  self.assertEqual(result['orders'][0]['zone_name'],'Doha')
  self.assertEqual(result['by_zone'][0]['label'],'Doha')
