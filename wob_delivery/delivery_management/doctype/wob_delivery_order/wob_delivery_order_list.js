frappe.listview_settings['WOB Delivery Order'] = {
	add_fields: ['delivery_status', 'company', 'assigned_driver', 'amount_to_collect', 'currency', 'scheduled_delivery_date'],
	get_indicator: function (doc) {
		const colors = {
			'Pending': 'orange',
			'Ready for Dispatch': 'blue',
			'Assigned': 'cyan',
			'Out for Delivery': 'purple',
			'Delivered': 'green',
			'Failed': 'red',
			'Rescheduled': 'yellow',
			'Cancelled': 'gray'
		};
		return [__(doc.delivery_status), colors[doc.delivery_status] || 'blue', 'delivery_status,=,' + doc.delivery_status];
	}
};
