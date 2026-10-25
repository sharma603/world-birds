frappe.ui.form.on('WOB Delivery Order', {
	setup(frm) {
		frm.set_query('payment_mode', () => ({query:'wob_delivery.bank_setup.payment_mode_query',filters:{company:frm.doc.company}}));
		frm.set_query('delivery_zone', () => ({
			filters: { company: frm.doc.company, active: 1 }
		}));
		for (const [field, dt] of [
			['sales_order', 'Sales Order'],
			['sales_invoice', 'Sales Invoice'],
			['delivery_note', 'Delivery Note']
		]) {
			frm.set_query(field, () => ({
				filters: { company: frm.doc.company, docstatus: 1 }
			}));
		}
		frm.set_query('assigned_driver', () => ({
			query: 'wob_delivery.api.driver_query',
			filters: { company: frm.doc.company, delivery_zone: frm.doc.delivery_zone }
		}));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.scheduled_delivery_date) {
			frm.set_value('scheduled_delivery_date', frappe.datetime.get_today());
		}
	},

	refresh(frm) {
        wob_delivery_payment_checkboxes(frm);
		wob_delivery_render_overview(frm);
		frm.toggle_display('dispatch_section', !frm.is_new());
		// Set dynamic colored status indicator on the page header
		const status_colors = {
			'Pending': 'orange',
			'Ready for Dispatch': 'blue',
			'Assigned': 'cyan',
			'Out for Delivery': 'purple',
			'Delivered': 'green',
			'Failed': 'red',
			'Rescheduled': 'yellow',
			'Cancelled': 'gray'
		};
		const status = frm.doc.delivery_status || 'Pending';
		frm.page.set_indicator(status, status_colors[status] || 'blue');
		frm.toggle_reqd('assigned_driver', ['Assigned', 'Out for Delivery', 'Delivered', 'Failed'].includes(status));

		// Driver assignment workflow rule:
		// New orders must be created in Pending status first. Drivers are assigned after save.
		if (frm.is_new()) {
			frm.set_df_property('assigned_driver', 'read_only', 1);
			frm.set_df_property('assigned_driver', 'description', __('Optional: save without a driver, mark Ready for Dispatch, then assign later.'));
			frm.set_df_property('delivery_status', 'read_only', 1);
			frm.set_df_property('delivery_status', 'description', __('New orders start in Pending status.'));
			if (frm.doc.assigned_driver) {
				frm.set_value('assigned_driver', null);
			}
			if (frm.doc.delivery_status !== 'Pending') {
				frm.set_value('delivery_status', 'Pending');
			}
		} else {
			frm.set_df_property('assigned_driver', 'read_only', status === 'Pending' ? 1 : 0);
			frm.set_df_property('assigned_driver', 'description', __('Optional until assigned. Mark Ready for Dispatch to select an eligible company/zone driver. Dispatch requires a valid driver.'));
			frm.set_df_property('delivery_status', 'read_only', 0);
			frm.set_df_property('delivery_status', 'description', '');
		}

		// Dashboard status banner
		if (!frm.is_new()) {
			frm.dashboard.clear_headline();
			if (frm.doc.delivery_status === 'Delivered') {
				frm.dashboard.set_headline_alert(
					`<span class="indicator green"><b>Delivered</b> ${frm.doc.completed_at ? 'on ' + frappe.datetime.str_to_user(frm.doc.completed_at) : ''}</span>`
				);
			} else if (frm.doc.delivery_status === 'Out for Delivery') {
				frm.dashboard.set_headline_alert(
					`<span class="indicator purple"><b>Out for Delivery</b> ${frm.doc.assigned_driver ? '· Driver: <b>' + frm.doc.assigned_driver + '</b>' : ''}</span>`
				);
			} else if (frm.doc.delivery_status === 'Assigned') {
				frm.dashboard.set_headline_alert(
					`<span class="indicator cyan"><b>Assigned</b> to Driver: <b>${frm.doc.assigned_driver || '-'}</b></span>`
				);
			} else if (frm.doc.delivery_status === 'Failed') {
				frm.dashboard.set_headline_alert(
					`<span class="indicator red"><b>Delivery Failed</b> — Please review override reason or reschedule.</span>`
				);
			} else if (frm.doc.delivery_status === 'Rescheduled') {
				frm.dashboard.set_headline_alert(
					`<span class="indicator yellow"><b>Rescheduled</b> for ${frappe.datetime.str_to_user(frm.doc.scheduled_delivery_date)}</span>`
				);
			}

			// Lifecycle Workflow Buttons
			if (frm.doc.delivery_status === 'Pending') {
				frm.add_custom_button(__('Mark Ready for Dispatch'), async () => {
					await frm.set_value('delivery_status', 'Ready for Dispatch');
					await frm.save();
				}).addClass('btn-primary');
			} else if (frm.doc.delivery_status === 'Ready for Dispatch') {
				// Driver can now be assigned
			} else if (frm.doc.delivery_status === 'Assigned') {
				frm.add_custom_button(__('Dispatch (Out for Delivery)'), async () => {
					await frm.set_value('delivery_status', 'Out for Delivery');
					await frm.save();
				}).addClass('btn-primary');
			} else if (frm.doc.delivery_status === 'Out for Delivery') {
				frm.add_custom_button(__('Mark Delivered'), async () => {
					frappe.confirm(__('Confirm delivery completion for this order?'), async () => {
						await frm.set_value('delivery_status', 'Delivered');
						await frm.save();
					});
				}).addClass('btn-success');

				frm.add_custom_button(__('Mark Failed'), () => {
					frappe.prompt([
						{ fieldname: 'reason', fieldtype: 'Small Text', label: __('Failure / Override Reason'), reqd: 1 }
					], async (values) => {
						await frm.set_value('change_reason', values.reason);
						await frm.set_value('delivery_status', 'Failed');
						await frm.save();
					}, __('Record Delivery Failure'), __('Submit'));
				}).addClass('btn-danger');
			}

			if (status !== 'Delivered') {
			// Recommend Drivers button
			const recommend_btn = frm.add_custom_button(__('Recommend Drivers'), async () => {
				if (!frm.doc.delivery_zone) {
					frappe.msgprint(__('Please select a Delivery Zone first.'));
					return;
				}
				const r = await frappe.call({
					method: 'wob_delivery.api.get_driver_recommendations',
					args: {
						company: frm.doc.company,
						delivery_zone: frm.doc.delivery_zone
					}
				});
				const rows = r.message || [];
				const d = new frappe.ui.Dialog({
					title: __('Zone Driver Recommendations'),
					fields: [{ fieldname: 'drivers', fieldtype: 'HTML' }]
				});
				const container = d.fields_dict.drivers.$wrapper;
				$('<p class="text-muted small mb-3">').text(
					__('Available drivers ranked by capacity and zone priority. Selection validates automatically upon save.')
				).appendTo(container);

				rows.forEach(row => {
					const badge_class = row.can_assign ? 'badge-success' : 'badge-secondary';
					const avail_badge = `<span class="badge ${badge_class} mr-1">${row.availability_status}</span>`;
					const type_badge = `<span class="badge badge-info mr-1">${row.assignment_type}</span>`;
					const load_text = `<span>Active: <b>${row.active_deliveries}</b>${row.maximum_active_deliveries ? '/' + row.maximum_active_deliveries : ''}</span>`;

					const card = $(`
						<div class="border rounded p-2 mb-2 d-flex justify-content-between align-items-center" style="background: var(--fg-color, #fff);">
							<div>
								<div class="font-weight-bold">${frappe.utils.escape_html(row.driver_name)} <span class="text-muted small">(${row.driver})</span></div>
								<div class="small mt-1">${type_badge} ${avail_badge} ${load_text}</div>
							</div>
							<button class="btn btn-sm ${row.can_assign ? 'btn-primary' : 'btn-default'}" ${!row.can_assign ? 'disabled' : ''}>
								${__('Assign')}
							</button>
						</div>
					`).appendTo(container);

					card.find('button').on('click', async () => {
						if (frm.doc.assigned_driver && frm.doc.assigned_driver !== row.driver && !frm.doc.change_reason) {
							frappe.msgprint(__('Enter a Reassignment Reason first.'));
							return;
						}
						d.hide();

						// If Pending, advance to Ready for Dispatch first as required by domain rules
						if (frm.doc.delivery_status === 'Pending') {
							await frm.set_value('delivery_status', 'Ready for Dispatch');
							await frm.save();
						}

						await frm.set_value('assigned_driver', row.driver);
						if (['Ready for Dispatch', 'Rescheduled'].includes(frm.doc.delivery_status)) {
							await frm.set_value('delivery_status', 'Assigned');
						}
						await frm.save();
					});
				});

				if (!rows.length) {
					$('<div class="alert alert-warning">').html(
						`<b>${__('No drivers assigned to this zone')}</b><br>` +
						__('Please ensure a Driver is assigned to this Company and Zone in <i>WOB Driver Zone Assignment</i> with status "Available".')
					).appendTo(container);
				}
				d.show();
			});

			if (frm.doc.delivery_status === 'Ready for Dispatch') {
				recommend_btn.addClass('btn-primary');
			}

			}

			// History button
			frm.add_custom_button(__('Assignment History'), () => {
				frappe.set_route('List', 'WOB Delivery Assignment History', { delivery_order: frm.doc.name });
			});

			// Map button
			if (frm.doc.latitude && frm.doc.longitude) {
				frm.add_custom_button(__('View on Map'), () => {
					window.open(`https://www.google.com/maps/search/?api=1&query=${frm.doc.latitude},${frm.doc.longitude}`, '_blank');
				}, __('Navigation'));
			} else if (frm.doc.customer_delivery_address) {
				frm.add_custom_button(__('View Address on Map'), () => {
					window.open(`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(frm.doc.customer_delivery_address)}`, '_blank');
				}, __('Navigation'));
			}

			// Source document links
			if (frm.doc.sales_invoice) {
				frm.add_custom_button(__('Open Sales Invoice'), () => {
					frappe.set_route('Form', 'Sales Invoice', frm.doc.sales_invoice);
				}, __('Related'));
			}
			if (frm.doc.delivery_note) {
				frm.add_custom_button(__('Open Delivery Note'), () => {
					frappe.set_route('Form', 'Delivery Note', frm.doc.delivery_note);
				}, __('Related'));
			}
			if (frm.doc.sales_order) {
				frm.add_custom_button(__('Open Sales Order'), () => {
					frappe.set_route('Form', 'Sales Order', frm.doc.sales_order);
				}, __('Related'));
			}

			// Print source documents & delivery order
			const has_dn = Boolean(frm.doc.delivery_note);
			const has_si = Boolean(frm.doc.sales_invoice);
			const has_so = Boolean(frm.doc.sales_order);

			if (has_dn) {
				frm.add_custom_button(__('Print Delivery Note'), () => {
					wob_delivery_print('Delivery Note', frm.doc.delivery_note, 'Alam Trading Delivery Note');
				}, __('Print'));
			}
			if (has_si) {
				frm.add_custom_button(__('Print Sales Invoice'), () => {
					wob_delivery_print('Sales Invoice', frm.doc.sales_invoice, 'Alam Trading Sales Invoice');
				}, __('Print'));
			}
			if (has_dn && has_si) {
				frm.add_custom_button(__('Print Both (Invoice & DN)'), () => {
					wob_delivery_print_both(frm.doc.delivery_note, frm.doc.sales_invoice);
				}, __('Print'));
			}
			if (has_so) {
				frm.add_custom_button(__('Print Sales Order'), () => {
					wob_delivery_print('Sales Order', frm.doc.sales_order, 'WOB Sales Order Delivery Slip');
				}, __('Print'));
			}
			frm.add_custom_button(__('Print Delivery Order'), () => {
				wob_delivery_print('WOB Delivery Order', frm.doc.name, 'WOB Delivery Slip');
			}, __('Print'));

			// If Sales Order is linked but Delivery Note and Sales Invoice are missing, offer Create button
			if (status !== 'Delivered' && has_so && !has_dn && !has_si) {
				frm.add_custom_button(__('Create Delivery Note & Invoice'), async () => {
					frappe.confirm(__('Create and submit Delivery Note and Sales Invoice for this order?'), async () => {
						try {
							if (frappe.dom && frappe.dom.freeze) frappe.dom.freeze(__('Creating Delivery Note and Sales Invoice...'));
							const r = await frappe.call({
								method: 'wob_delivery.api.create_fulfillment_documents',
								args: { delivery_order: frm.doc.name }
							});
							if (frappe.dom && frappe.dom.unfreeze) frappe.dom.unfreeze();
							if (r.message && (r.message.delivery_note || r.message.sales_invoice)) {
								if (frappe.show_alert) {
									frappe.show_alert({
										message: __('Delivery Note and Sales Invoice created successfully.'),
										indicator: 'green'
									});
								}
								await frm.reload_doc();
							}
						} catch (e) {
							if (frappe.dom && frappe.dom.unfreeze) frappe.dom.unfreeze();
							frappe.msgprint({
								title: __('Cannot Create Fulfillment Documents'),
								message: e.message || __('An error occurred while creating documents.'),
								indicator: 'red'
							});
						}
					});
				}).addClass('btn-primary');

				if (frappe.call) {
					frappe.call({
						method: 'wob_delivery.api.sync_fulfillment_documents',
						args: { delivery_order: frm.doc.name }
					}).then(r => {
						if (r && r.message && r.message.synced) {
							frm.reload_doc();
						}
					});
				}
			}

			// Link field descriptions with Quick Print & Open links
			if (frm.doc.delivery_note) {
				frm.set_df_property('delivery_note', 'description',
					`<span class="text-muted">${__('Linked')}: </span>` +
					`<a href="#" onclick="frappe.set_route('Form', 'Delivery Note', '${frappe.utils.escape_html(frm.doc.delivery_note)}'); return false;"><b>${frappe.utils.escape_html(frm.doc.delivery_note)}</b></a> · ` +
					`<a href="#" onclick="wob_delivery_print('Delivery Note', '${frappe.utils.escape_html(frm.doc.delivery_note)}', 'Alam Trading Delivery Note'); return false;"><b>📄 ${__('Print Preview')}</b></a> · ` +
					`<a href="/printview?doctype=Delivery%20Note&name=${encodeURIComponent(frm.doc.delivery_note)}&format=Alam%20Trading%20Delivery%20Note&trigger_print=1" target="_blank"><b>🖨️ ${__('Quick Print')}</b></a>`
				);
			} else {
				frm.set_df_property('delivery_note', 'description', __('No Delivery Note linked.'));
			}

			if (frm.doc.sales_invoice) {
				frm.set_df_property('sales_invoice', 'description',
					`<span class="text-muted">${__('Linked')}: </span>` +
					`<a href="#" onclick="frappe.set_route('Form', 'Sales Invoice', '${frappe.utils.escape_html(frm.doc.sales_invoice)}'); return false;"><b>${frappe.utils.escape_html(frm.doc.sales_invoice)}</b></a> · ` +
					`<a href="#" onclick="wob_delivery_print('Sales Invoice', '${frappe.utils.escape_html(frm.doc.sales_invoice)}', 'Alam Trading Sales Invoice'); return false;"><b>📄 ${__('Print Preview')}</b></a> · ` +
					`<a href="/printview?doctype=Sales%20Invoice&name=${encodeURIComponent(frm.doc.sales_invoice)}&format=Alam%20Trading%20Sales%20Invoice&trigger_print=1" target="_blank"><b>🖨️ ${__('Quick Print')}</b></a>`
				);
			} else {
				frm.set_df_property('sales_invoice', 'description', __('No Sales Invoice linked.'));
			}

			if (frm.doc.sales_order) {
				frm.set_df_property('sales_order', 'description',
					`<span class="text-muted">${__('Linked')}: </span>` +
					`<a href="#" onclick="frappe.set_route('Form', 'Sales Order', '${frappe.utils.escape_html(frm.doc.sales_order)}'); return false;"><b>${frappe.utils.escape_html(frm.doc.sales_order)}</b></a> · ` +
					`<a href="#" onclick="wob_delivery_print('Sales Order', '${frappe.utils.escape_html(frm.doc.sales_order)}', 'WOB Sales Order Delivery Slip'); return false;"><b>📄 ${__('Print Preview')}</b></a> · ` +
					`<a href="/printview?doctype=Sales%20Order&name=${encodeURIComponent(frm.doc.sales_order)}&format=WOB%20Sales%20Order%20Delivery%20Slip&trigger_print=1" target="_blank"><b>🖨️ ${__('Quick Print')}</b></a>`
				);
			}

			// Call customer shortcut
			if (frm.doc.customer_phone_number) {
				frm.add_custom_button(__('Call Customer'), () => {
					window.open(`tel:${frm.doc.customer_phone_number}`);
				}, __('Contact'));
			}
		}
		if (!frm.is_new() && status === 'Delivered') {
			frm.disable_form();
			frm.dashboard.set_headline_alert(__('Delivered — this delivery order is locked and cannot be edited.'));
		}

	},

	async assigned_driver(frm) {
		if (frm.is_new()) return;
		if (frm.doc.assigned_driver && ['Ready for Dispatch', 'Rescheduled'].includes(frm.doc.delivery_status)) {
			await frm.set_value('delivery_status', 'Assigned');
		} else if (!frm.doc.assigned_driver && frm.doc.delivery_status === 'Assigned') {
			await frm.set_value('delivery_status', 'Ready for Dispatch');
		}
		frm.toggle_reqd('assigned_driver', ['Assigned', 'Out for Delivery', 'Delivered', 'Failed'].includes(frm.doc.delivery_status));
		wob_delivery_render_overview(frm);
	},

	delivery_status: wob_delivery_render_overview,
	scheduled_delivery_date: wob_delivery_render_overview,
	customer: wob_delivery_render_overview,
	delivery_zone: wob_delivery_render_overview,

	company(frm) {
        frm.set_value({payment_mode:null,collection_bank_account:null,allowed_payment_modes:null});
        wob_delivery_payment_checkboxes(frm);
		frm.set_value('delivery_zone', null);
		frm.set_value('sales_order', null);
		frm.set_value('sales_invoice', null);
		frm.set_value('delivery_note', null);
		wob_delivery_render_overview(frm);
	},

	async sales_order(frm) {
		await wob_delivery_preview(frm, 'sales_order', 'Sales Order');
	},

	async sales_invoice(frm) {
		await wob_delivery_preview(frm, 'sales_invoice', 'Sales Invoice');
	},

	async delivery_note(frm) {
		await wob_delivery_preview(frm, 'delivery_note', 'Delivery Note');
	}
});

async function wob_delivery_preview(frm, field, doctype) {
	if (!frm.doc.company || !frm.doc[field]) return;
	const r = await frappe.call({
		method: 'wob_delivery.api.get_source_preview',
		args: {
			company: frm.doc.company,
			source_type: doctype,
			source_name: frm.doc[field]
		}
	});
	const data = r.message || {};
	for (const key of ['customer', 'customer_phone_number', 'currency']) {
		if (data[key]) await frm.set_value(key, data[key]);
	}
	if (!frm.doc.customer_delivery_address && data.customer_delivery_address) {
		await frm.set_value('customer_delivery_address', data.customer_delivery_address);
	}
}

function wob_delivery_render_overview(frm) {
	if (!frm.$wrapper) return;
	frm.$wrapper.addClass('wob-delivery-order-form');
	const layout = frm.$wrapper.find('.form-layout').first();
	let overview = layout.children('.wob-delivery-overview');
	if (!overview.length) {
		layout.prepend('<section class="wob-delivery-overview" aria-label="Delivery overview"></section>');
		overview = layout.children('.wob-delivery-overview');
	}
	overview.html(wob_delivery_overview_html(frm.doc, frm.is_new()));
}

function wob_delivery_overview_html(doc, is_new) {
	const escape = value => frappe.utils.escape_html(String(value || ''));
	const status = doc.delivery_status || 'Pending';
	const hints = {
		'Pending': __('Complete the destination details and save. You can assign a driver later.'),
		'Ready for Dispatch': __('Ready for assignment. Choose an eligible driver when you are ready.'),
		'Assigned': __('Driver assigned. Review the delivery details before dispatch.'),
		'Out for Delivery': __('Delivery in progress. Track the driver and record the outcome.'),
		'Delivered': __('Delivery complete. Review the record and assignment history below.'),
		'Failed': __('Review the failure reason before rescheduling this delivery.'),
		'Rescheduled': __('Confirm the new delivery date and driver assignment.'),
		'Cancelled': __('This delivery is cancelled. Its history remains available for review.')
	};
	const facts = [
		[__('Company'), doc.company || __('Select company')],
		[__('Customer'), doc.customer || __('From linked sales document')],
		[__('Scheduled delivery'), doc.scheduled_delivery_date ? (frappe.datetime.str_to_user(doc.scheduled_delivery_date) + (doc.scheduled_delivery_time ? ' • ' + doc.scheduled_delivery_time : '')) : __('Not scheduled')],
		[__('Driver'), doc.assigned_driver || __('Not assigned')]
	];
	const hint = is_new && doc.sales_order && !doc.delivery_note && !doc.sales_invoice
		? __('Saving automatically submits a Delivery Note and Sales Invoice, posting stock and accounts. Confirm the warehouse and stock first. A driver can be assigned later.')
		: (hints[status] || '');
	return `<div class="wob-overview-top">
		<div><div class="wob-overview-eyebrow">${escape(__('DELIVERY OPERATIONS'))}</div>
		<h2>${escape(is_new ? __('New delivery') : doc.name)}</h2></div>
		<span class="wob-overview-status" data-status="${escape(status)}"><span aria-hidden="true"></span>${escape(__(status))}</span>
	</div>
	<p class="wob-overview-hint">${escape(hint)}</p>
	<dl class="wob-overview-facts">${facts.map(([label, value]) => `<div><dt>${escape(label)}</dt><dd title="${escape(value)}">${escape(value)}</dd></div>`).join('')}</dl>`;
}

function wob_delivery_print(doctype, name, format) {
	if (!doctype || !name) return null;
	const format_param = format ? `&format=${encodeURIComponent(format)}` : '';
	const base_url = `/printview?doctype=${encodeURIComponent(doctype)}&name=${encodeURIComponent(name)}${format_param}`;
	const trigger_url = `${base_url}&trigger_print=1`;
	const full_url = (typeof frappe !== 'undefined' && frappe.urllib && frappe.urllib.get_full_url)
		? frappe.urllib.get_full_url(trigger_url)
		: trigger_url;

	if (typeof frappe !== 'undefined' && frappe.ui && frappe.ui.Dialog) {
		const preview_url = (frappe.urllib && frappe.urllib.get_full_url)
			? frappe.urllib.get_full_url(base_url)
			: base_url;
		const pdf_url = (frappe.urllib && frappe.urllib.get_full_url)
			? frappe.urllib.get_full_url(`/api/method/frappe.utils.print_format.download_pdf?doctype=${encodeURIComponent(doctype)}&name=${encodeURIComponent(name)}${format_param}`)
			: `/api/method/frappe.utils.print_format.download_pdf?doctype=${encodeURIComponent(doctype)}&name=${encodeURIComponent(name)}${format_param}`;

		const title = `${doctype} ${name}`;
		const d = new frappe.ui.Dialog({
			title: __('Print: {0}', [title]),
			size: 'extra-large',
			fields: [
				{
					fieldtype: 'HTML',
					fieldname: 'preview_html',
					options: `
						<div class="wob-print-modal-container" style="display:flex; flex-direction:column; height:74vh; width:100%;">
							<div class="wob-print-toolbar" style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; margin-bottom:8px;">
								<div style="font-weight:600; font-size:13px; color:#334155;">
									<span class="indicator-pill blue" style="margin-right:6px;"></span>${frappe.utils.escape_html(doctype)}: <b>${frappe.utils.escape_html(name)}</b>
									${format ? `<span class="text-muted" style="margin-left:8px; font-weight:normal;">(${frappe.utils.escape_html(format)})</span>` : ''}
								</div>
								<div style="display:flex; gap:8px;">
									<button type="button" class="btn btn-primary btn-sm wob-direct-print-btn" style="font-weight:600;">
										🖨️ ${__('Print')}
									</button>
									<a href="${pdf_url}" target="_blank" class="btn btn-default btn-sm" style="text-decoration:none;">
										📥 ${__('Download PDF')}
									</a>
									<a href="${preview_url}" target="_blank" class="btn btn-default btn-sm" style="text-decoration:none;">
										↗️ ${__('Open in New Tab')}
									</a>
								</div>
							</div>
							<div style="flex:1; width:100%; border:1px solid #cbd5e1; border-radius:6px; overflow:hidden; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,0.06);">
								<iframe class="wob-print-iframe" src="${preview_url}" style="width:100%; height:100%; border:none;" title="${frappe.utils.escape_html(title)}"></iframe>
							</div>
						</div>
					`
				}
			],
			primary_action_label: __('Print'),
			primary_action() {
				print_active_iframe();
			}
		});

		function print_active_iframe() {
			const iframe = d.$wrapper.find('iframe.wob-print-iframe')[0];
			if (iframe && iframe.contentWindow) {
				try {
					iframe.contentWindow.focus();
					iframe.contentWindow.print();
				} catch (e) {
					window.open(full_url, '_blank');
				}
			} else {
				window.open(full_url, '_blank');
			}
		}

		if (d.$wrapper) {
			d.$wrapper.addClass('wob-print-dialog');
			d.$wrapper.find('.wob-direct-print-btn').on('click', print_active_iframe);
		}

		d.show();
	} else if (typeof window !== 'undefined' && window.open) {
		window.open(full_url, '_blank');
	}
	return full_url;
}

function wob_delivery_print_both(dn_name, si_name) {
	if (!dn_name && !si_name) return null;
	if (!dn_name) return wob_delivery_print('Sales Invoice', si_name);
	if (!si_name) return wob_delivery_print('Delivery Note', dn_name);

	const dn_base_url = `/printview?doctype=Delivery%20Note&name=${encodeURIComponent(dn_name)}&format=Alam%20Trading%20Delivery%20Note`;
	const si_base_url = `/printview?doctype=Sales%20Invoice&name=${encodeURIComponent(si_name)}&format=Alam%20Trading%20Sales%20Invoice`;
	const dn_url = (typeof frappe !== 'undefined' && frappe.urllib && frappe.urllib.get_full_url)
		? frappe.urllib.get_full_url(dn_base_url) : dn_base_url;
	const si_url = (typeof frappe !== 'undefined' && frappe.urllib && frappe.urllib.get_full_url)
		? frappe.urllib.get_full_url(si_base_url) : si_base_url;

	const dn_pdf = `/api/method/frappe.utils.print_format.download_pdf?doctype=Delivery%20Note&name=${encodeURIComponent(dn_name)}&format=Alam%20Trading%20Delivery%20Note`;
	const si_pdf = `/api/method/frappe.utils.print_format.download_pdf?doctype=Sales%20Invoice&name=${encodeURIComponent(si_name)}&format=Alam%20Trading%20Sales%20Invoice`;

	if (typeof frappe !== 'undefined' && frappe.ui && frappe.ui.Dialog) {
		let current_tab = 'dn';
		const d = new frappe.ui.Dialog({
			title: __('Print: Delivery Note & Sales Invoice'),
			size: 'extra-large',
			fields: [
				{
					fieldtype: 'HTML',
					fieldname: 'both_preview_html',
					options: `
						<div class="wob-print-modal-container" style="display:flex; flex-direction:column; height:74vh; width:100%;">
							<div class="wob-print-tabs-bar" style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; margin-bottom:8px;">
								<div class="btn-group btn-group-sm" role="group">
									<button type="button" class="btn btn-primary wob-tab-btn wob-tab-dn" style="font-weight:600;">
										📄 ${__('Delivery Note')}: ${frappe.utils.escape_html(dn_name)}
									</button>
									<button type="button" class="btn btn-default wob-tab-btn wob-tab-si" style="font-weight:600;">
										📄 ${__('Sales Invoice')}: ${frappe.utils.escape_html(si_name)}
									</button>
								</div>
								<div style="display:flex; gap:8px;">
									<button type="button" class="btn btn-primary btn-sm wob-print-current-btn" style="font-weight:600;">
										🖨️ ${__('Print Current')}
									</button>
									<button type="button" class="btn btn-default btn-sm wob-print-both-btn" style="font-weight:600;">
										🖨️ ${__('Print Both')}
									</button>
									<a href="${dn_pdf}" target="_blank" class="btn btn-default btn-sm wob-pdf-dn-btn" style="text-decoration:none;">
										📥 ${__('DN PDF')}
									</a>
									<a href="${si_pdf}" target="_blank" class="btn btn-default btn-sm wob-pdf-si-btn" style="text-decoration:none;">
										📥 ${__('Invoice PDF')}
									</a>
								</div>
							</div>
							<div style="flex:1; width:100%; border:1px solid #cbd5e1; border-radius:6px; overflow:hidden; background:#fff; position:relative; box-shadow:0 1px 3px rgba(0,0,0,0.06);">
								<iframe class="wob-iframe-dn" src="${dn_url}" style="width:100%; height:100%; border:none; display:block;" title="Delivery Note"></iframe>
								<iframe class="wob-iframe-si" src="${si_url}" style="width:100%; height:100%; border:none; display:none;" title="Sales Invoice"></iframe>
							</div>
						</div>
					`
				}
			],
			primary_action_label: __('Print Current'),
			primary_action() {
				print_frame(current_tab === 'dn' ? '.wob-iframe-dn' : '.wob-iframe-si');
			}
		});

		function print_frame(selector) {
			const iframe = d.$wrapper.find(selector)[0];
			if (iframe && iframe.contentWindow) {
				try {
					iframe.contentWindow.focus();
					iframe.contentWindow.print();
				} catch (e) {
					window.open(selector === '.wob-iframe-dn' ? `${dn_url}&trigger_print=1` : `${si_url}&trigger_print=1`, '_blank');
				}
			}
		}

		function print_both_frames() {
			print_frame('.wob-iframe-dn');
			setTimeout(() => {
				print_frame('.wob-iframe-si');
			}, 1200);
		}

		if (d.$wrapper) {
			d.$wrapper.addClass('wob-print-dialog');
			const $wrapper = d.$wrapper;
			$wrapper.find('.wob-tab-dn').on('click', function() {
				current_tab = 'dn';
				$wrapper.find('.wob-tab-dn').removeClass('btn-default').addClass('btn-primary');
				$wrapper.find('.wob-tab-si').removeClass('btn-primary').addClass('btn-default');
				$wrapper.find('.wob-iframe-dn').show();
				$wrapper.find('.wob-iframe-si').hide();
			});

			$wrapper.find('.wob-tab-si').on('click', function() {
				current_tab = 'si';
				$wrapper.find('.wob-tab-si').removeClass('btn-default').addClass('btn-primary');
				$wrapper.find('.wob-tab-dn').removeClass('btn-primary').addClass('btn-default');
				$wrapper.find('.wob-iframe-si').show();
				$wrapper.find('.wob-iframe-dn').hide();
			});

			$wrapper.find('.wob-print-current-btn').on('click', function() {
				print_frame(current_tab === 'dn' ? '.wob-iframe-dn' : '.wob-iframe-si');
			});

			$wrapper.find('.wob-print-both-btn').on('click', function() {
				print_both_frames();
			});
		}

		d.show();
	} else if (typeof window !== 'undefined' && window.open) {
		window.open(`${dn_url}&trigger_print=1`, '_blank');
		window.open(`${si_url}&trigger_print=1`, '_blank');
	}

	return { dn_url, si_url };
}

if (typeof window !== 'undefined') {
	window.wob_delivery_print = wob_delivery_print;
	window.wob_delivery_print_both = wob_delivery_print_both;
}



async function wob_delivery_payment_checkboxes(frm) {
    if (!frm || !frm.fields_dict || !frm.fields_dict.payment_methods_html) return;
    const field=frm.fields_dict.payment_methods_html;
    const wrapper=field.$wrapper, company=frm.doc ? frm.doc.company : null;
    const sequence=frm.__wob_payment_sequence=(frm.__wob_payment_sequence||0)+1;
    wrapper.off('.wobPayments').empty();
    $('<div class="control-label"></div>').text(__('Payment Methods')).appendTo(wrapper);
    if(!company){$('<p class="text-muted"></p>').text(__('Choose a Company to see active payment methods.')).appendTo(wrapper);return;}
    $('<p class="text-muted wob-payment-loading"></p>').text(__('Loading active payment methods…')).appendTo(wrapper);
    try {
        const result=await frappe.call({method:'wob_delivery.bank_setup.get_active_payment_methods',args:{company}});
        if(sequence!==frm.__wob_payment_sequence||!frm.doc||frm.doc.company!==company)return;
        wrapper.find('.wob-payment-loading').remove();
        const methods=result.message||[];
        let selected=[];
        try {
            if (Array.isArray(frm.doc.allowed_payment_modes)) {
                selected = frm.doc.allowed_payment_modes;
            } else if (frm.doc.allowed_payment_modes) {
                selected = JSON.parse(frm.doc.allowed_payment_modes);
            } else if (frm.doc.payment_mode) {
                selected = [frm.doc.payment_mode];
            }
        } catch(error) {
            selected = [];
        }
        if(!methods.length)$('<p class="text-muted"></p>').text(__('No active payment methods have been created.')).appendTo(wrapper);
        methods.forEach(method=>{
            const row=$('<label class="wob-payment-method" style="display:flex;align-items:flex-start;gap:10px;padding:10px 0;cursor:pointer"></label>').appendTo(wrapper);
            $('<input type="checkbox" class="wob-payment-tick" style="margin-top:4px">').attr('data-mode',method.mode_of_payment).attr('aria-label',method.mode_of_payment).prop('checked',selected.includes(method.mode_of_payment)).prop('disabled',frm.doc.delivery_status==='Delivered'||(!method.configured&&!selected.includes(method.mode_of_payment))).appendTo(row);
            const text=$('<span></span>').appendTo(row);
            $('<strong></strong>').text(method.mode_of_payment).appendTo(text);
            $('<small style="display:block" class="text-muted"></small>').text(method.configured?`${method.type} · ${method.account}`:method.reason).appendTo(text);
        });
        $('<p class="text-muted"></p>').text(__('Tick the methods the delivery person may use to collect payment.')).appendTo(wrapper);
        wrapper.on('change.wobPayments','.wob-payment-tick',async()=>{
            const checked=wrapper.find('.wob-payment-tick:checked').map((i,input)=>$(input).attr('data-mode')).get();
            const chosen=methods.filter(method=>checked.includes(method.mode_of_payment));
            await frm.set_value({allowed_payment_modes:JSON.stringify(checked),payment_mode:checked.length===1?checked[0]:null,collection_bank_account:chosen.length===1?chosen[0].account:null});
            if(chosen.length)await frm.set_value('payment_type',chosen.every(method=>method.type==='Bank')?'Bank Transfer':'Cash on Delivery');
        });
    } catch(error){if(sequence===frm.__wob_payment_sequence){wrapper.find('.wob-payment-loading').text(__('Unable to load payment methods. Reload the form to retry.'));}}
}
