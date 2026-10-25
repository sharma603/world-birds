import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from wob_delivery import api, services


class OptionalDriverTests(unittest.TestCase):
    def test_unassigned_pre_dispatch_orders_are_valid(self):
        for status in ('Pending', 'Ready for Dispatch', 'Rescheduled'):
            with self.subTest(status=status), patch.object(services, 'lock_record') as lock:
                services.validate_driver(SimpleNamespace(assigned_driver=None, delivery_status=status))
                lock.assert_not_called()

    def test_dispatch_and_assigned_states_require_driver(self):
        for status in ('Assigned', 'Out for Delivery', 'Delivered', 'Failed'):
            with self.subTest(status=status), patch.object(frappe, 'throw', side_effect=ValueError):
                with self.assertRaises(ValueError):
                    services.validate_driver(SimpleNamespace(assigned_driver=None, delivery_status=status))

    def test_selected_driver_still_requires_company_zone_mapping(self):
        doc = SimpleNamespace(assigned_driver='DRIVER-1', company='Alam Trading',
                              delivery_zone='Doha', delivery_status='Assigned')
        driver = SimpleNamespace(name='DRIVER-1', status='Active', user='driver@example.com')
        with patch.object(services, 'lock_record'), patch.object(frappe, 'get_doc', return_value=driver), \
             patch.object(frappe, 'db', new=Mock()) as db, \
             patch.object(frappe, 'throw', side_effect=ValueError):
            db.get_value.side_effect = [1, None]
            with self.assertRaises(ValueError):
                services.validate_driver(doc)

    def test_picker_only_returns_eligible_matching_drivers(self):
        rows = [dict(driver='D1', driver_name='Ali', can_assign=True),
                dict(driver='D2', driver_name='Ali unavailable', can_assign=False),
                dict(driver='D3', driver_name='Sara', can_assign=True)]
        with patch.object(api, 'get_driver_recommendations', return_value=rows):
            self.assertTrue(callable(getattr(api, 'driver_query', None)), 'Eligible driver search is missing')
            result = api.driver_query('Driver', 'ali', 'name', 0, 20,
                                      {'company': 'Alam Trading', 'delivery_zone': 'Doha'})
        self.assertEqual(result, [('D1', 'Ali')])

    def test_picker_without_company_or_zone_returns_no_drivers(self):
        self.assertTrue(callable(getattr(api, 'driver_query', None)), 'Eligible driver search is missing')
        self.assertEqual(api.driver_query('Driver', '', 'name', 0, 20, {}), [])


if __name__ == '__main__':
    unittest.main()
