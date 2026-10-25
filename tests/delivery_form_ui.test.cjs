const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const context = { __: value => value, frappe: {
  ui: { form: { on() {} } },
  datetime: { str_to_user: value => value },
  utils: { escape_html: value => String(value).replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;') },
} };
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,
  '../wob_delivery/delivery_management/doctype/wob_delivery_order/wob_delivery_order.js'), 'utf8'), context);

test('delivery overview safely renders customer data and an unassigned draft', () => {
  assert.equal(typeof context.wob_delivery_overview_html, 'function');
  const html = context.wob_delivery_overview_html({
    company: 'Alam Trading', customer: '<img src=x onerror=alert(1)>',
    delivery_status: 'Pending', scheduled_delivery_date: '2026-10-22',
  }, true);
  assert.ok(html.includes('&lt;img'));
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('Not assigned'));
  assert.ok(html.includes('New delivery'));
});

test('overview reflects the actual delivery state without treating cancellation as completion', () => {
  assert.equal(typeof context.wob_delivery_overview_html, 'function');
  const html = context.wob_delivery_overview_html({name: 'WOB-DEL-1', delivery_status: 'Cancelled',
    company: 'Alam Trading', assigned_driver: 'DRIVER-1'}, false);
  assert.ok(html.includes('Cancelled'));
  assert.ok(html.includes('DRIVER-1'));
  assert.ok(!html.includes('Delivery complete'));
});

test('new Sales Order deliveries explain that Save submits stock and accounting documents', () => {
  const html = context.wob_delivery_overview_html({sales_order: 'SO-1', delivery_status: 'Pending'}, true);
  assert.ok(html.includes('automatically submits'));
  assert.ok(html.includes('Delivery Note'));
  assert.ok(html.includes('Sales Invoice'));
});

test('wob_delivery_print builds proper print view URL with trigger_print', () => {
  assert.equal(typeof context.wob_delivery_print, 'function');
  const url = context.wob_delivery_print('Delivery Note', 'DN-001');
  assert.ok(url.includes('/printview?doctype=Delivery%20Note&name=DN-001&trigger_print=1'));
  const invUrl = context.wob_delivery_print('Sales Invoice', 'INV-001');
  assert.ok(invUrl.includes('/printview?doctype=Sales%20Invoice&name=INV-001&trigger_print=1'));
});

test('form registers print and related actions for source documents', () => {
  let formHandler;
  const ctx = {
    __: (v, args) => (args ? v.replace(/\{(\d+)\}/g, (_, i) => args[i]) : v),
    frappe: {
      ui: { form: { on: (_dt, h) => { formHandler = h; } } },
      datetime: { str_to_user: v => v },
      utils: { escape_html: v => String(v) },
      urllib: { get_full_url: u => u }
    }
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname,
    '../wob_delivery/delivery_management/doctype/wob_delivery_order/wob_delivery_order.js'), 'utf8'), ctx);

  const customButtons = [];
  const fieldProperties = {};
  let locked = false;
  const mockFrm = {
    is_new: () => false,
    disable_form() { locked = true; },
    doc: {
      name: 'WOB-DEL-1',
      delivery_status: 'Delivered',
      delivery_note: 'DN-123',
      sales_invoice: 'INV-456',
      sales_order: 'SO-789'
    },
    page: { set_indicator() {} },
    dashboard: { clear_headline() {}, set_headline_alert() {} },
    toggle_display() {},
    toggle_reqd() {},
    add_custom_button(label, action, group) {
      customButtons.push({ label, action, group });
      return { addClass() { return this; } };
    },
    set_df_property(field, prop, val) {
      fieldProperties[`${field}.${prop}`] = val;
    }
  };

  formHandler.refresh(mockFrm);

  const labels = customButtons.map(b => b.label);
  assert.equal(locked, true, 'Delivered form must be read-only');
  assert.ok(!labels.includes('Recommend Drivers'));
  assert.ok(!labels.includes('Create Delivery Note & Invoice'));
  const printButtons = customButtons.filter(b => b.group === 'Print').map(b => b.label);
  const relatedButtons = customButtons.filter(b => b.group === 'Related').map(b => b.label);

  assert.ok(printButtons.includes('Print Delivery Note'));
  assert.ok(printButtons.includes('Print Sales Invoice'));
  assert.ok(printButtons.includes('Print Both (Invoice & DN)'));
  assert.ok(printButtons.includes('Print Sales Order'));
  assert.ok(printButtons.includes('Print Delivery Order'));

  assert.ok(relatedButtons.includes('Open Delivery Note'));
  assert.ok(relatedButtons.includes('Open Sales Invoice'));
  assert.ok(relatedButtons.includes('Open Sales Order'));

  assert.ok(fieldProperties['delivery_note.description'].includes('Print'));
  assert.ok(fieldProperties['sales_invoice.description'].includes('Print'));
  assert.ok(fieldProperties['sales_order.description'].includes('Print'));
});

test('print buttons open in-page Dialog preview without redirecting route', () => {
  let dialogCreated = null;
  let routeCalled = false;

  class MockDialog {
    constructor(opts) {
      this.opts = opts;
      this.shown = false;
      this.$wrapper = {
        addClass() {},
        find() {
          return {
            on() {},
            show() {},
            hide() {},
            removeClass() { return this; }
          };
        }
      };
      dialogCreated = this;
    }
    show() {
      this.shown = true;
    }
  }

  const ctx = {
    __: (v, args) => (args ? v.replace(/\{(\d+)\}/g, (_, i) => args[i]) : v),
    frappe: {
      ui: {
        form: { on() {} },
        Dialog: MockDialog
      },
      set_route: () => {
        routeCalled = true;
      },
      datetime: { str_to_user: v => v },
      utils: { escape_html: v => String(v) },
      urllib: { get_full_url: u => u }
    }
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname,
    '../wob_delivery/delivery_management/doctype/wob_delivery_order/wob_delivery_order.js'), 'utf8'), ctx);

  // Test single print dialog
  ctx.wob_delivery_print('Sales Order', 'SO-001', 'WOB Sales Order Delivery Slip');
  assert.ok(dialogCreated !== null, 'Dialog should be opened');
  assert.ok(dialogCreated.shown, 'Dialog should be shown');
  assert.ok(dialogCreated.opts.title.includes('Sales Order SO-001'));
  assert.ok(dialogCreated.opts.fields[0].options.includes('WOB Sales Order Delivery Slip'));
  assert.equal(routeCalled, false, 'frappe.set_route must NEVER be called');

  // Test print both dialog
  dialogCreated = null;
  ctx.wob_delivery_print_both('DN-001', 'INV-001');
  assert.ok(dialogCreated !== null, 'Dialog should be opened for both');
  assert.ok(dialogCreated.shown, 'Dialog should be shown');
  assert.ok(dialogCreated.opts.title.includes('Delivery Note & Sales Invoice'));
  assert.equal(routeCalled, false, 'frappe.set_route must NEVER be called');
});


