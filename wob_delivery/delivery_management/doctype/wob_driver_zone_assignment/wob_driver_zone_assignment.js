frappe.ui.form.on('WOB Driver Zone Assignment', {
 setup(frm) {
  frm.set_query('delivery_zone',()=>({filters:{company:frm.doc.company,active:1}}));
  frm.set_query('driver',()=>({filters:{status:'Active'}}));
 }
});
