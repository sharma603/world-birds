const test = require('node:test');
const assert = require('node:assert/strict');
const {createSyncService, escapeHTML, actionsFor} = require('../wob_delivery/delivery_management/page/wob_delivery_dashboard/wob_delivery_dashboard.js');
const tick = () => new Promise(resolve => setImmediate(resolve));
test('record values are escaped and delivered actions are immutable', () => {
 assert.equal(escapeHTML('<img onerror="x">&'), '&lt;img onerror=&quot;x&quot;&gt;&amp;');
 assert.deepEqual(actionsFor('Delivered'), []);
 assert.deepEqual(actionsFor('Out for Delivery'), ['delivered', 'failed']);
});
test('same request deduplicates, changed scope rejects stale response', async () => {
 const pending=[], rendered=[]; let scope={company:'A'};
 const service=createSyncService({fetch:args=>new Promise(resolve=>pending.push({args,resolve})),args:()=>scope,render:value=>rendered.push(value),error:()=>{}});
 service.start(); service.refresh(); assert.equal(pending.length,1);
 scope={company:'B'};service.refresh();assert.equal(pending.length,2);
 pending[1].resolve('B');await tick();pending[0].resolve('A');await tick();assert.deepEqual(rendered,['B']);service.stop();
});
test('events coalesce and changes during an in-flight request reconcile afterwards', async () => {
 const pending=[];let count=0;
 const service=createSyncService({fetch:()=>{count++;return new Promise(resolve=>pending.push(resolve));},args:()=>({}),render:()=>{},error:()=>{},debounce:5});
 service.start(); service.changed(); service.changed(); pending.shift()({});await new Promise(r=>setTimeout(r,15));assert.equal(count,2);pending.shift()({});await tick();service.stop();
});
test('stop invalidates pending responses and cancels scheduled work; restart loads fresh data', async () => {
 const pending=[],rendered=[];
 const service=createSyncService({fetch:()=>new Promise(resolve=>pending.push(resolve)),args:()=>({}),render:x=>rendered.push(x),error:()=>{}});
 service.start();service.changed();service.stop();pending.shift()('old');await tick();assert.deepEqual(rendered,[]);service.start();pending.shift()('new');await tick();assert.deepEqual(rendered,['new']);service.stop();
});
test('returning to a previous scope while requests are pending renders that scope', async () => {
 let scope='A';const pending=[],rendered=[];
 const service=createSyncService({args:()=>({scope}),fetch:args=>new Promise(resolve=>pending.push({scope:args.scope,resolve})),render:x=>rendered.push(x),error:()=>{}});
 service.start();scope='B';service.refresh();scope='A';service.refresh();
 for(const req of pending)req.resolve(req.scope);await tick();assert.deepEqual(rendered,['A']);service.stop();
});
test('LAN development socket preserves manager options and adds site header once', () => {
 const {configureDevSocket} = require('../wob_delivery/delivery_management/page/wob_delivery_dashboard/wob_delivery_dashboard.js');
 const socket={io:{opts:{transports:['polling','websocket'],extraHeaders:{'X-Existing':'kept'},reconnectionAttempts:3}}};
 const context={dev_server:true,hostname:'192.168.1.25',sitename:'birds.local'};
 assert.equal(configureDevSocket(socket,context),true);
 assert.deepEqual(socket.io.opts.transports,['polling']);
 assert.deepEqual(socket.io.opts.extraHeaders,{'X-Existing':'kept','X-Frappe-Site-Name':'birds.local'});
 assert.equal(socket.io.opts.reconnectionAttempts,3);
 assert.equal(configureDevSocket(socket,context),false);
});
test('production, matched hosts and localhost sockets remain untouched', () => {
 const {configureDevSocket} = require('../wob_delivery/delivery_management/page/wob_delivery_dashboard/wob_delivery_dashboard.js');
 for(const context of [{dev_server:false,hostname:'192.168.1.25',sitename:'birds.local'},{dev_server:true,hostname:'birds.local',sitename:'birds.local'},{dev_server:true,hostname:'localhost',sitename:'birds.local'},{dev_server:true,hostname:'127.0.0.1',sitename:'birds.local'}]) {
  const socket={io:{opts:{transports:['websocket'],extraHeaders:{Existing:'yes'}}}}, before=JSON.stringify(socket);
  assert.equal(configureDevSocket(socket,context),false);assert.equal(JSON.stringify(socket),before);
 }
});
