frappe.ui.form.on('Sales Order', {
	refresh(frm) {
		if (frm.doc.custom_wob_delivery_status) {
			const colors = { Delivered: 'green', Failed: 'red', Cancelled: 'gray',
				Assigned: 'cyan', 'Out for Delivery': 'blue', 'Ready for Dispatch': 'blue' };
			frm.dashboard.add_indicator(__('Delivery: {0}', [frm.doc.custom_wob_delivery_status]),
				colors[frm.doc.custom_wob_delivery_status] || 'orange');
		}
		const staff = frappe.session.user === 'Administrator' || [
			'System Manager', 'WOB Delivery Administrator',
			'WOB Delivery Manager', 'WOB Delivery Dispatcher'
		].some(role => frappe.user.has_role(role));
		if (!staff || !frappe.model.can_create('WOB Delivery Order') || frm.doc.docstatus !== 1 ||
			['Closed', 'Cancelled', 'On Hold'].includes(frm.doc.status)) return;

		frm.add_custom_button(__('Delivery Order'), async () => {
			// The preview checks source read permission and company access on the server.
			// Saving the delivery performs authoritative source and duplicate checks.
			const { message: preview } = await frappe.call({
				method: 'wob_delivery.api.get_source_preview',
				args: {
					company: frm.doc.company,
					source_type: 'Sales Order',
					source_name: frm.doc.name
				},
				freeze: true,
				freeze_message: __('Preparing Delivery Order...')
			});
			await frappe.new_doc('WOB Delivery Order', {
				company: frm.doc.company,
				sales_order: frm.doc.name,
				scheduled_delivery_date: frm.doc.delivery_date || frappe.datetime.get_today(),
				delivery_status: 'Pending',
				customer: preview.customer,
				currency: preview.currency,
				customer_phone_number: preview.customer_phone_number,
				customer_delivery_address: preview.customer_delivery_address
			});
		}, __('Create'));
	}
});
