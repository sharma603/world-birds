import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

import frappe
from wob_delivery import sales_order_status as status
from wob_delivery.delivery_management.doctype.wob_delivery_order import wob_delivery_order as controller


class SalesOrderStatusTests(unittest.TestCase):
    def test_latest_active_task_wins_over_old_completed_or_cancelled_tasks(self):
        rows = [dict(name='OLD', delivery_status='Delivered', creation='2026-10-20'),
                dict(name='ACTIVE', delivery_status='Out for Delivery', creation='2026-10-21'),
                dict(name='CANCELLED', delivery_status='Cancelled', creation='2026-10-22')]
        self.assertEqual(status.select_delivery(rows)['name'], 'ACTIVE')

    def test_latest_created_task_is_used_when_all_tasks_are_terminal(self):
        rows = [dict(name='OLD', delivery_status='Delivered', creation='2026-10-20'),
                dict(name='NEW', delivery_status='Cancelled', creation='2026-10-22')]
        self.assertEqual(status.select_delivery(rows)['delivery_status'], 'Cancelled')
        self.assertIsNone(status.select_delivery([]))

    def test_sync_updates_only_logistics_fields_and_notifies_sales_order(self):
        doc = SimpleNamespace(sales_order='SO-1', sales_invoice=None, delivery_note=None, company='Alam Trading')
        db = Mock()
        db.get_value.return_value = frappe._dict(company='Alam Trading', custom_wob_delivery_status='Assigned',
                                                 custom_wob_delivery_order='DEL-1')
        db.sql.return_value = [dict(name='DEL-1', delivery_status='Delivered', creation='2026-10-22')]
        sales_order = Mock()
        with patch.object(frappe, 'db', new=db), patch.object(frappe, 'get_doc', return_value=sales_order):
            status.sync_sales_order_status(doc)
        db.set_value.assert_called_once_with('Sales Order', 'SO-1', {
            'custom_wob_delivery_status': 'Delivered', 'custom_wob_delivery_order': 'DEL-1'})
        sales_order.notify_update.assert_called_once()

    def test_invoice_only_delivery_resolves_its_sales_order(self):
        doc = SimpleNamespace(sales_order=None, sales_invoice='INV-1', delivery_note=None)
        with patch.object(frappe, 'get_all', return_value=['SO-1', 'SO-1', None]):
            self.assertEqual(status.related_sales_orders(doc), {'SO-1'})

    def test_delivery_save_hook_syncs_both_new_and_existing_deliveries(self):
        for old in (None, object()):
            doc = Mock()
            doc.get_doc_before_save.return_value = old
            with patch.object(controller, 'record_history'), patch.object(controller, 'publish_delivery_update') as publish, patch.object(controller, 'sync_sales_order_status') as sync:
                controller.WOBDeliveryOrder.on_update(doc)
            sync.assert_called_once_with(doc)
            publish.assert_called_once_with(doc)

    def test_delivery_note_only_resolves_its_sales_order(self):
        doc = SimpleNamespace(sales_order=None, sales_invoice=None, delivery_note='DN-1')
        with patch.object(frappe, 'get_all', return_value=['SO-2']):
            self.assertEqual(status.related_sales_orders(doc), {'SO-2'})

    def test_sync_rejects_cross_company_sales_order(self):
        doc = SimpleNamespace(sales_order='SO-1', sales_invoice=None, delivery_note=None, company='Alam Trading')
        db = Mock()
        db.get_value.return_value = frappe._dict(company='Birds Center')
        with patch.object(frappe, 'db', new=db), patch.object(frappe, 'throw', side_effect=ValueError):
            with self.assertRaises(ValueError):
                status.sync_sales_order_status(doc)
        db.set_value.assert_not_called()


if __name__ == '__main__':
    unittest.main()
