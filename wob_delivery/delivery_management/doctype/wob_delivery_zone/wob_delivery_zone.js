frappe.ui.form.on('WOB Delivery Zone', {
	setup(frm) {
		// Set filter for company if needed
	},

	refresh(frm) {
		// Form header indicator
		if (frm.doc.active) {
			frm.page.set_indicator(__('Active'), 'green');
		} else {
			frm.page.set_indicator(__('Inactive'), 'darkgrey');
		}

		if (!frm.is_new()) {
			// Quick Action: Assign Driver to this zone
			frm.add_custom_button(__('Assign Driver'), () => {
				frappe.new_doc('WOB Driver Zone Assignment', {
					company: frm.doc.company,
					delivery_zone: frm.doc.name
				});
			}, __('Actions'));

			// Quick Action: View Delivery Orders in this zone
			frm.add_custom_button(__('View Delivery Orders'), () => {
				frappe.set_route('List', 'WOB Delivery Order', {
					delivery_zone: frm.doc.name
				});
			}, __('Related'));

			// Quick Action: View Driver Zone Assignments
			frm.add_custom_button(__('Driver Assignments'), () => {
				frappe.set_route('List', 'WOB Driver Zone Assignment', {
					delivery_zone: frm.doc.name
				});
			}, __('Related'));
		}
	},

	company(frm) {
		if (frm.doc.company) {
			frappe.db.get_value('Company', frm.doc.company, 'default_currency', (r) => {
				if (r && r.default_currency) {
					frm.set_value('currency', r.default_currency);
				}
			});
		}
	},

	zone_code(frm) {
		if (frm.doc.zone_code) {
			frm.set_value('zone_code', frm.doc.zone_code.toUpperCase().trim());
		}
	}
});
