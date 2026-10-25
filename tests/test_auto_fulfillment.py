import importlib
import unittest
from unittest.mock import Mock, patch

import frappe


class AutoFulfillmentTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('wob_delivery.auto_fulfillment'),
                             'Automatic delivery-note/invoice creation is missing')
        return importlib.import_module('wob_delivery.auto_fulfillment')

    def delivery(self, **values):
        doc = Mock()
        doc.sales_order = 'SO-1'
        doc.sales_invoice = None
        doc.delivery_note = None
        doc.company = 'Alam Trading'
        for key, value in values.items():
            setattr(doc, key, value)
        return doc

    def test_creates_and_submits_linked_note_then_invoice_without_double_stock_posting(self):
        module = self.module()
        doc = self.delivery()
        note = Mock(name='note')
        note.name = 'DN-1'
        invoice = Mock(name='invoice')
        invoice.name = 'INV-1'
        invoice.update_stock = 0
        calls = Mock()
        calls.attach_mock(note, 'note')
        calls.attach_mock(invoice, 'invoice')
        with patch.object(module, 'make_delivery_note', return_value=note), \
             patch.object(module, 'make_sales_invoice', return_value=invoice) as mapper, \
             patch.object(module, 'lock_record'), \
             patch.object(frappe, 'has_permission', return_value=True), \
             patch.object(frappe, 'db', new=Mock(sql=Mock(return_value=[]))), \
             patch.object(module, 'validate_sources'):
            module.create_submitted_documents(doc)
        self.assertLess(calls.mock_calls.index(unittest.mock.call.note.submit()),
                        calls.mock_calls.index(unittest.mock.call.invoice.insert()))
        mapper.assert_called_once_with('DN-1')
        self.assertEqual(invoice.update_stock, 0)
        doc.db_set.assert_any_call({'delivery_note': 'DN-1', 'sales_invoice': 'INV-1'},
                                   update_modified=False)

    def test_existing_source_links_are_not_posted_again(self):
        module = self.module()
        with patch.object(module, 'make_delivery_note') as mapper:
            module.create_submitted_documents(self.delivery(sales_invoice='INV-EXISTING'))
            module.create_submitted_documents(self.delivery(delivery_note='DN-EXISTING'))
        mapper.assert_not_called()

    def test_existing_draft_or_submitted_documents_prevent_duplicates(self):
        module = self.module()
        with patch.object(module, 'make_delivery_note') as mapper, \
             patch.object(module, 'lock_record'), \
             patch.object(frappe, 'has_permission', return_value=True), \
             patch.object(frappe, 'db', new=Mock(sql=Mock(return_value=[{'name':'EXISTING'}]))), \
             patch.object(frappe, 'throw', side_effect=ValueError):
            with self.assertRaises(ValueError):
                module.create_submitted_documents(self.delivery())
        mapper.assert_not_called()

    def test_insufficient_permissions_do_not_create_documents(self):
        module = self.module()
        with patch.object(module, 'make_delivery_note') as mapper, \
             patch.object(frappe, 'has_permission', return_value=False), \
             patch.object(frappe, 'throw', side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                module.create_submitted_documents(self.delivery())
        mapper.assert_not_called()

    def test_invoice_failure_propagates_for_request_transaction_rollback(self):
        module = self.module()
        note, invoice = Mock(), Mock()
        note.name = 'DN-1'
        invoice.update_stock = 0
        invoice.submit.side_effect = ValueError('Accounting setup is incomplete')
        with patch.object(module, 'make_delivery_note', return_value=note), \
             patch.object(module, 'make_sales_invoice', return_value=invoice), \
             patch.object(module, 'lock_record'), \
             patch.object(frappe, 'has_permission', return_value=True), \
             patch.object(frappe, 'db', new=Mock(sql=Mock(return_value=[]))) as db:
            with self.assertRaises(ValueError):
                module.create_submitted_documents(self.delivery())
        db.commit.assert_not_called()
        db.rollback.assert_called_once_with(save_point='wob_auto_fulfillment')

    def test_first_save_creates_documents_before_recording_history(self):
        self.module()
        from wob_delivery.delivery_management.doctype.wob_delivery_order import wob_delivery_order as controller
        calls = Mock()
        with patch.object(controller, 'create_submitted_documents') as create, \
             patch.object(controller, 'record_history') as history:
            calls.attach_mock(create, 'create')
            calls.attach_mock(history, 'history')
            doc = self.delivery()
            controller.WOBDeliveryOrder.after_insert(doc)
        self.assertEqual(calls.mock_calls, [unittest.mock.call.create(doc), unittest.mock.call.history(doc)])

    def test_sync_fulfillment_documents_links_existing_submitted_dn_and_si(self):
        import wob_delivery.api as api
        doc = self.delivery(sales_order='SO-1', delivery_note=None, sales_invoice=None)
        db_mock = Mock(get_value=Mock(return_value='Alam Trading'),
                       sql=Mock(side_effect=[
                           [{'parent': 'DN-LINKED-1'}],
                           [{'parent': 'INV-LINKED-1'}]
                       ]))
        with patch.object(frappe, 'get_doc', return_value=doc), \
             patch.object(frappe, 'db', new=db_mock), \
             patch.object(api, 'assert_company'), \
             patch.object(api, 'lock_record'), \
             patch('wob_delivery.services.validate_sources'):
            res = api.sync_fulfillment_documents('WOB-DEL-1')
        self.assertTrue(res['synced'])
        self.assertEqual(res['updated']['delivery_note'], 'DN-LINKED-1')
        self.assertEqual(res['updated']['sales_invoice'], 'INV-LINKED-1')

    def test_empty_sales_references_can_be_populated_without_immutable_error(self):
        from wob_delivery.services import validate_order
        doc_data = {
            'company': 'Alam Trading',
            'sales_order': 'SO-1',
            'delivery_note': 'DN-1',
            'sales_invoice': 'INV-1'
        }
        doc = Mock()
        doc.is_new.return_value = False
        doc.name = 'WOB-DEL-1'
        doc.company = 'Alam Trading'
        doc.get.side_effect = lambda k, d=None: doc_data.get(k, d)
        doc.delivery_status = 'Pending'
        doc.change_reason = None
        doc.assigned_driver = None

        old = Mock()
        old_data = {
            'company': 'Alam Trading',
            'sales_order': 'SO-1',
            'delivery_note': None,
            'sales_invoice': None,
            'delivery_status': 'Pending',
            'assigned_driver': None,
            'created_by': 'Administrator',
            'completed_at': None
        }
        old.company = 'Alam Trading'
        old.assigned_driver = None
        old.delivery_status = 'Pending'
        old.get.side_effect = lambda k, d=None: old_data.get(k, d)
        old.as_dict.return_value = old_data

        doc.get_doc_before_save.return_value = old

        zone = Mock(company='Alam Trading', active=1)
        with patch('wob_delivery.services.assert_company'), \
             patch('wob_delivery.services.lock_record'), \
             patch('wob_delivery.services.role_kind', return_value='Administrator'), \
             patch('wob_delivery.services.check_transition'), \
             patch.object(frappe, 'get_doc', return_value=zone), \
             patch('wob_delivery.services.validate_sources'), \
             patch('wob_delivery.services.validate_driver'):
            # Should not raise immutable error
            validate_order(doc)

    def test_changing_already_populated_sales_reference_throws_immutable_error(self):
        from wob_delivery.services import validate_order
        doc_data = {
            'sales_order': 'SO-1',
            'delivery_note': 'DN-2',
            'sales_invoice': 'INV-1'
        }
        doc = Mock()
        doc.is_new.return_value = False
        doc.name = 'WOB-DEL-1'
        doc.company = 'Alam Trading'
        doc.get.side_effect = lambda k, d=None: doc_data.get(k, d)

        old_data = {
            'company': 'Alam Trading',
            'sales_order': 'SO-1',
            'delivery_note': 'DN-1',
            'sales_invoice': 'INV-1'
        }
        old = Mock()
        old.get.side_effect = lambda k, d=None: old_data.get(k, d)

        doc.get_doc_before_save.return_value = old

        with patch('wob_delivery.services.assert_company'), \
             patch('wob_delivery.services.lock_record'), \
             patch.object(frappe, 'throw', side_effect=ValueError('Sales references are immutable')):
            with self.assertRaises(ValueError) as ctx:
                validate_order(doc)
            self.assertIn('Sales references are immutable', str(ctx.exception))

    def test_delivery_order_can_be_deleted_with_history_cleanup(self):
        from wob_delivery.delivery_management.doctype.wob_delivery_order.wob_delivery_order import WOBDeliveryOrder
        doc = Mock(spec=WOBDeliveryOrder)
        doc.name = 'WOB-DEL-1'
        doc.company = 'Alam Trading'
        doc.delivery_status = 'Pending'
        doc.delivery_status = 'Pending'
        db_mock = Mock()
        with patch('wob_delivery.delivery_management.doctype.wob_delivery_order.wob_delivery_order.assert_company'), \
             patch.object(frappe, 'db', new=db_mock):
            WOBDeliveryOrder.on_trash(doc)
            db_mock.delete.assert_called_once_with('WOB Delivery Assignment History', {'delivery_order': 'WOB-DEL-1'})
            self.assertEqual(db_mock.set_value.call_count, 2)





if __name__ == '__main__':
    unittest.main()
