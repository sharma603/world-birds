const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('sales document dialog initializes a valid type before its automatic search', async () => {
 const source = fs.readFileSync('wob_delivery/delivery_management/page/wob_delivery_dashboard/wob_delivery_dashboard.js', 'utf8');
 const start = source.indexOf("  page.add_inner_button(__('From Sales Document')");
 const end = source.indexOf("  page.add_inner_button(__('Delivery Register')", start);
 let open, dialog; const calls=[];
 const wrapper = {html(){return this},empty(){return this}};
 class Dialog {
  constructor(options) {
   dialog=this;this.options=options;this.fields_dict={results_html:{$wrapper:wrapper}};
   // Frappe normalizes string defaults to lowercase; Select values are case-sensitive.
   this.value=options.fields.find(f=>f.fieldname==='source_type').default?.toLowerCase();
  }
  show(){}
  async set_value(field,value){await Promise.resolve();this.value=value;}
  get_primary_btn(){return {trigger:()=>{
   assert(['Sales Order','Sales Invoice','Delivery Note'].includes(this.value),'required Document Type must be initialized before search');
   return this.options.primary_action({source_type:this.value});
  }}}
 }
 vm.runInNewContext(source.slice(start,end),{page:{add_inner_button:(label,action)=>{open=action}},controls:{company:{get_value:()=>''}},frappe:{ui:{Dialog},call:async args=>{calls.push(args);return {message:[]}}},__:s=>s});
 await open();
 assert.equal(calls[0].args.source_type,'Sales Order');
 await dialog.set_value('source_type','Sales Invoice');
 await dialog.get_primary_btn().trigger('click');
 assert.equal(calls[1].args.source_type,'Sales Invoice');
});
