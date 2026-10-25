const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
let handlers;
vm.runInNewContext(fs.readFileSync(path.join(__dirname,
  '../wob_delivery/delivery_management/doctype/wob_delivery_order/wob_delivery_order.js'), 'utf8'), {
  frappe: { ui: { form: { on: (_doctype, value) => { handlers = value; } } },
    datetime: { str_to_user: (value) => value } },
  __: (text) => text,
});

function form(status, driver = null) {
  return {
    doc: { delivery_status: status, assigned_driver: driver, company: 'Alam Trading', delivery_zone: 'Doha' },
    async set_value(field, value) { this.doc[field] = value; },
    is_new: () => false,
    toggle_reqd() {},
  };
}

test('form permits saving without a driver before assignment but requires one for dispatch', () => {
  for (const [status, required] of [['Pending', false], ['Ready for Dispatch', false],
      ['Rescheduled', false], ['Assigned', true], ['Out for Delivery', true]]) {
    const frm = form(status);
    const requirements = {};
    frm.toggle_reqd = (field, value) => { requirements[field] = value; };
    frm.set_df_property = () => {};
    frm.toggle_display = () => {};
    frm.page = { set_indicator() {} };
    frm.dashboard = { clear_headline() {}, set_headline_alert() {} };
    frm.add_custom_button = () => ({ addClass() {} });
    handlers.refresh(frm);
    assert.equal(requirements.assigned_driver, required, status);
  }
});

test('selecting a driver after preparation sets Assigned status', async () => {
  for (const status of ['Ready for Dispatch', 'Rescheduled']) {
    const frm = form(status, 'DRIVER-1');
    await handlers.assigned_driver(frm);
    assert.equal(frm.doc.delivery_status, 'Assigned');
  }
});

test('clearing an Assigned driver returns the order to a savable pre-dispatch state', async () => {
  const frm = form('Assigned');
  await handlers.assigned_driver(frm);
  assert.equal(frm.doc.delivery_status, 'Ready for Dispatch');
});

test('clearing a dispatched driver does not downgrade its status or bypass server checks', async () => {
  const frm = form('Out for Delivery');
  await handlers.assigned_driver(frm);
  assert.equal(frm.doc.delivery_status, 'Out for Delivery');
});
