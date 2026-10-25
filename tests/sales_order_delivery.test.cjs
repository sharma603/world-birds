const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load({ canCreate = true, roles = ['WOB Delivery Dispatcher'] } = {}) {
  let handler;
  const created = [];
  const calls = [];
  const frappe = {
    ui: { form: { on: (_doctype, value) => { handler = value; } } },
    model: { can_create: () => canCreate },
    user: { has_role: (role) => roles.includes(role) },
    session: { user: 'dispatcher@example.com' },
    datetime: { get_today: () => '2026-10-22' },
    call: async (options) => {
      calls.push(options);
      return { message: { customer: 'Customer 1', currency: 'QAR',
        customer_phone_number: '12345', customer_delivery_address: 'Doha' } };
    },
    new_doc: async (doctype, values) => { created.push({ doctype, ...values }); },
  };
  const file = path.join(__dirname, '../wob_delivery/public/js/sales_order.js');
  vm.runInNewContext(fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '', {
    frappe, __: (text) => text,
  });
  assert.ok(handler, 'Sales Order delivery integration must register a form handler');
  return { handler, created, calls };
}

function form(overrides = {}) {
  const buttons = [];
  return {
    doc: { name: 'SAL-ORD-1', company: 'Alam Trading', docstatus: 1,
      status: 'To Deliver and Bill', delivery_date: '2026-10-25', ...overrides },
    buttons,
    add_custom_button(label, action, group) { buttons.push({ label, action, group }); },
  };
}

test('Create menu opens linked unassigned delivery with source preview and planned date', async () => {
  const { handler, calls, created } = load();
  const frm = form();
  handler.refresh(frm);
  assert.equal(frm.buttons.length, 1);
  assert.equal(frm.buttons[0].label, 'Delivery Order');
  assert.equal(frm.buttons[0].group, 'Create');
  await frm.buttons[0].action();
  assert.equal(calls[0].args.source_name, 'SAL-ORD-1');
  assert.equal(calls[0].args.company, 'Alam Trading');
  assert.equal(created[0].doctype, 'WOB Delivery Order');
  assert.equal(created[0].sales_order, 'SAL-ORD-1');
  assert.equal(created[0].company, 'Alam Trading');
  assert.equal(created[0].customer, 'Customer 1');
  assert.equal(created[0].customer_delivery_address, 'Doha');
  assert.equal(created[0].scheduled_delivery_date, '2026-10-25');
  assert.equal(created[0].delivery_status, 'Pending');
  assert.ok(!created[0].assigned_driver);
});

test('draft, cancelled and held orders cannot start delivery creation', () => {
  const { handler } = load();
  for (const override of [{ docstatus: 0 }, { docstatus: 2 }, { status: 'Closed' },
      { status: 'Cancelled' }, { status: 'On Hold' }]) {
    const frm = form(override);
    handler.refresh(frm);
    assert.equal(frm.buttons.length, 0);
  }
});

test('users without delivery create permission or a staff role do not see the action', () => {
  for (const options of [{ canCreate: false }, { roles: ['WOB Delivery Driver'] }]) {
    const { handler } = load(options);
    const frm = form();
    handler.refresh(frm);
    assert.equal(frm.buttons.length, 0);
  }
});
