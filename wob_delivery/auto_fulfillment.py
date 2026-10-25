"""Create ERPNext fulfillment documents only on first save of a Sales Order task."""
import frappe
from wob_delivery.services import lock_record, validate_sources


def make_delivery_note(sales_order):
    from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note as mapper
    return mapper(sales_order)


def make_sales_invoice(delivery_note):
    from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice as mapper
    return mapper(delivery_note)


def create_submitted_documents(doc):
    # Existing submitted source documents keep their established workflow.
    if not doc.sales_order or doc.delivery_note or doc.sales_invoice:
        return
    for doctype in ('Delivery Note', 'Sales Invoice'):
        if not all(frappe.has_permission(doctype, ptype=action) for action in ('create', 'submit')):
            frappe.throw(f'Creating this delivery requires Create and Submit permissions for {doctype}.',
                         frappe.PermissionError)

    lock_record('Sales Order', doc.sales_order)
    existing = frappe.db.sql('''
        SELECT DISTINCT dn.name FROM `tabDelivery Note` dn
        JOIN `tabDelivery Note Item` dni ON dni.parent=dn.name
        WHERE dn.company=%s AND dni.against_sales_order=%s AND dn.docstatus<2
        UNION
        SELECT DISTINCT si.name FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent=si.name
        WHERE si.company=%s AND sii.sales_order=%s AND si.docstatus<2
        LIMIT 1
    ''', (doc.company, doc.sales_order, doc.company, doc.sales_order), as_dict=True)
    if existing:
        frappe.throw('This Sales Order already has a draft or submitted Delivery Note or Sales Invoice. '
                     'Review and link the existing submitted documents instead of creating duplicates.')

    # No commit here: delivery, stock, receivables and source links share the request transaction.
    frappe.db.savepoint('wob_auto_fulfillment')
    try:
        note = make_delivery_note(doc.sales_order)
        note.insert()
        note.submit()
        invoice = make_sales_invoice(note.name)
        invoice.update_stock = 0  # The Delivery Note is the sole stock-posting document.
        invoice.insert()
        invoice.submit()
        doc.db_set({'delivery_note': note.name, 'sales_invoice': invoice.name}, update_modified=False)
        # Refresh collection amount from the newly submitted invoice's outstanding balance.
        validate_sources(doc)
        doc.db_set({'amount_to_collect': doc.amount_to_collect,
                    'currency': doc.currency, 'active_fulfillment_key': doc.active_fulfillment_key},
                   update_modified=False)
    except Exception:
        frappe.db.rollback(save_point='wob_auto_fulfillment')
        raise
