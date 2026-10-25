"""Mirror logistics progress without changing ERPNext's stock/billing status."""
import frappe
from wob_delivery.domain import ACTIVE, STATUSES


def select_delivery(rows):
    if not rows:
        return None
    active = [row for row in rows if row['delivery_status'] in ACTIVE]
    return max(active or rows, key=lambda row: (str(row['creation']), row['name']))


def related_sales_orders(doc):
    orders = {doc.sales_order} if doc.sales_order else set()
    if doc.sales_invoice:
        orders.update(frappe.get_all('Sales Invoice Item', filters={'parent': doc.sales_invoice}, pluck='sales_order'))
    if doc.delivery_note:
        orders.update(frappe.get_all('Delivery Note Item', filters={'parent': doc.delivery_note}, pluck='against_sales_order'))
    return {name for name in orders if name}


def sync_sales_order_status(doc):
    for name in sorted(related_sales_orders(doc)):
        # Serialize competing deliveries for the same Sales Order, including backfills.
        frappe.db.sql('SELECT name FROM `tabSales Order` WHERE name=%s FOR UPDATE', (name,))
        current = frappe.db.get_value('Sales Order', name,
            ['company', 'custom_wob_delivery_status', 'custom_wob_delivery_order'], as_dict=True)
        if not current or current.company != doc.company:
            frappe.throw('Delivery and Sales Order must belong to the same company.')
        rows = frappe.db.sql('''
            SELECT DISTINCT d.name, d.delivery_status, d.creation
            FROM `tabWOB Delivery Order` d
            LEFT JOIN `tabSales Invoice Item` si ON si.parent=d.sales_invoice
            LEFT JOIN `tabDelivery Note Item` dn ON dn.parent=d.delivery_note
            WHERE d.company=%s AND (d.sales_order=%s OR si.sales_order=%s OR dn.against_sales_order=%s)
        ''', (doc.company, name, name, name), as_dict=True)
        latest = select_delivery(rows)
        values = {
            'custom_wob_delivery_status': latest['delivery_status'] if latest else None,
            'custom_wob_delivery_order': latest['name'] if latest else None,
        }
        if all(current.get(field) == value for field, value in values.items()):
            continue
        frappe.db.set_value('Sales Order', name, values)
        # Standard Frappe document/list notifications are emitted after commit.
        frappe.get_doc('Sales Order', name).notify_update()


def setup_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({'Sales Order': [
        {'fieldname': 'custom_wob_delivery_section', 'label': 'Delivery Tracking',
         'fieldtype': 'Section Break', 'insert_after': 'is_subcontracted'},
        {'fieldname': 'custom_wob_delivery_status', 'label': 'Delivery Order Status',
         'fieldtype': 'Select', 'options': '\n' + '\n'.join(STATUSES),
         'insert_after': 'custom_wob_delivery_section', 'read_only': 1,
         'allow_on_submit': 1, 'in_list_view': 1, 'in_standard_filter': 1, 'no_copy': 1},
        {'fieldname': 'custom_wob_delivery_column', 'fieldtype': 'Column Break',
         'insert_after': 'custom_wob_delivery_status'},
        {'fieldname': 'custom_wob_delivery_order', 'label': 'Delivery Order',
         'fieldtype': 'Link', 'options': 'WOB Delivery Order',
         'insert_after': 'custom_wob_delivery_column', 'read_only': 1,
         'allow_on_submit': 1, 'no_copy': 1},
    ]})


def backfill():
    for row in frappe.get_all('WOB Delivery Order',
            fields=['sales_order', 'sales_invoice', 'delivery_note', 'company'], order_by='creation asc'):
        sync_sales_order_status(row)
