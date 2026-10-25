/* One authoritative request service. Its sequence belongs to a visible page lifetime. */
function createSyncService(options) {
  let active = false, sequence = 0, timer = null, dirty = false, latestKey = null;
  const requests = new Map();
  function refresh(force = false) {
    if (!active) return Promise.resolve();
    const args = options.args(), key = JSON.stringify(args);
    if (requests.has(key) && key === latestKey) { if (force) dirty = true; return requests.get(key); }
    latestKey = key;
    const id = ++sequence;
    options.loading?.();
    const promise = Promise.resolve(options.fetch(args)).then(value => {
      if (active && id === sequence) options.render(value);
    }).catch(error => { if (active && id === sequence) options.error(error); }).finally(() => {
      if (requests.get(key) === promise) requests.delete(key);
      if (active && dirty && !requests.size) { dirty = false; changed(); }
    });
    requests.set(key, promise);
    return promise;
  }
  function changed() {
    if (!active) return;
    dirty = true;
    clearTimeout(timer);
    timer = setTimeout(() => { timer = null; if (!requests.size) { dirty = false; refresh(); } }, options.debounce ?? 250);
  }
  return {refresh, changed, start() { if (active) return; active = true; refresh(); }, stop() {
    active = false; sequence++; clearTimeout(timer); timer = null; dirty = false; requests.clear();
  }};
}
function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function actionsFor(status) {
  return ({Pending:['ready'], 'Ready for Dispatch':['assign'], Assigned:['assign','dispatch'], 'Out for Delivery':['delivered','failed']})[status] || [];
}
/* Frappe development sites can be opened through a LAN IP. The polling
 * handshake must identify the configured site, while retaining normal cookies. */
function configureDevSocket(socket, context) {
  const {dev_server, hostname, sitename} = context;
  if (!dev_server || !sitename || !hostname || hostname === sitename || ['localhost','127.0.0.1'].includes(hostname) || !socket?.io?.opts) return false;
  const managers = configureDevSocket.managers || (configureDevSocket.managers = new WeakSet());
  if (managers.has(socket.io)) return false;
  managers.add(socket.io);
  const options = socket.io.opts;
  options.extraHeaders = {...options.extraHeaders, 'X-Frappe-Site-Name':sitename};
  // Browsers cannot send custom headers in a websocket handshake.
  options.transports = ['polling'];
  return true;
}
if (typeof module !== 'undefined' && module.exports) module.exports = {createSyncService, escapeHTML, actionsFor, configureDevSocket};
if (typeof frappe !== 'undefined') {
frappe.pages['wob-delivery-dashboard'].on_page_load = function(wrapper) {
  wrapper.wobDashboard?.destroy();
  const page = frappe.ui.make_app_page({parent:wrapper,title:__('Delivery Control Center'),single_column:true});
  frappe.require('/assets/wob_delivery/css/wob_delivery_dashboard.css');
  const e = escapeHTML, controls = {}, labels = {ready:__('Mark Ready'),assign:__('Assign Driver'),dispatch:__('Dispatch'),delivered:__('Mark Delivered'),failed:__('Report Failure')};
  let visible = false, muted = false, data = null, pageNumber = 1, sortBy = 'scheduled_delivery_date', sortOrder = 'asc';
  let completedToday = 0, issuesOnly = 0, searchTimer, heartbeat, clockTimer, lastRequest = 0, lastDate = '', detail = null, detailSequence = 0;
  let retryAfter = 0, retryDelay = 5000, socket = null;
  const changes = new Map(), seen = new Set(), notifications = [], scopeOverrides = {};
  const root = $('<div class="wob-delivery-dashboard"></div>').appendTo(page.main);
  root.html(`<header class="wob-control-header"><div><div class="wob-eyebrow">ALAM TRADING · OPERATIONS</div><h1>${__('Delivery Control Center')}</h1><p>${__('Monitor, assign, dispatch and track deliveries in real time.')}</p><time class="wob-clock"></time></div><div class="wob-sync-meta"><span class="wob-connection offline" role="status">${__('Offline')}</span><span class="wob-last-sync">${__('Waiting for first sync')}</span><button class="btn btn-default btn-sm wob-notifications-toggle">${__('Updates')} <span class="wob-notification-count">0</span></button></div></header><div class="wob-notifications" hidden></div><details class="wob-filters" open><summary>${__('Smart filters')}<span>${__('All sections share this scope')}</span></summary><div class="wob-filter-grid"></div><div class="wob-filter-footer"><div class="wob-filter-chips"></div><button class="btn btn-sm btn-default wob-clear">${__('Clear All Filters')}</button></div></details><div class="wob-error" role="alert" hidden></div><div class="wob-kpi-grid"></div><div class="wob-analytics-grid"></div><section class="wob-orders-card"><div class="wob-orders-header"><div><h2>${__('Delivery Tasks')}</h2><span class="wob-total text-muted"></span></div><span class="text-muted">${__('Permission scoped')}</span></div><div class="wob-table-scroll"><table class="wob-table"><thead><tr><th>${__('Delivery ID')}</th><th>${__('Company')}</th><th>${__('Customer')}</th><th>${__('Zone')}</th><th>${__('Driver')}</th><th><button data-sort="delivery_status">${__('Status')} ↕</button></th><th><button data-sort="scheduled_delivery_date">${__('Scheduled')} ↕</button></th><th>${__('Payment')}</th><th>${__('Actions')}</th></tr></thead><tbody></tbody></table></div><div class="wob-mobile-orders"></div><footer class="wob-pagination"><span class="wob-page-label"></span><div><button class="btn btn-default btn-sm wob-prev">${__('Previous')}</button><button class="btn btn-default btn-sm wob-next">${__('Next')}</button></div></footer></section>`);
  const filterDefs = [
    {fieldname:'company',label:__('Company'),fieldtype:'Link',options:'Company'},
    {fieldname:'delivery_zone',label:__('Delivery Zone'),fieldtype:'Link',options:'WOB Delivery Zone'},
    {fieldname:'driver',label:__('Assigned Driver'),fieldtype:'Link',options:'Driver'},
    {fieldname:'from_date',label:__('Date From'),fieldtype:'Date'},
    {fieldname:'to_date',label:__('Date To'),fieldtype:'Date'},
    {fieldname:'status',label:__('Delivery Status'),fieldtype:'Select',options:'\nPending\nReady for Dispatch\nAssigned\nOut for Delivery\nDelivered\nFailed\nRescheduled\nCancelled'},
    {fieldname:'customer_search',label:__('Customer Search'),fieldtype:'Data'},
    {fieldname:'order_search',label:__('Order Number Search'),fieldtype:'Data'}
  ];
  filterDefs.forEach(def => {
    const parent = $('<div></div>').appendTo(root.find('.wob-filter-grid'));
    controls[def.fieldname] = frappe.ui.form.make_control({parent,df:{...def,change:() => {
      if (muted) return;
      delete scopeOverrides[def.fieldname];
      if (def.fieldname === 'status') {completedToday = 0; issuesOnly = 0;}
      pageNumber = 1; clearTimeout(searchTimer); searchTimer = setTimeout(() => {chips(); service.refresh();},def.fieldtype === 'Data' ? 350 : 0);
    }},render_input:true});
  });
  function args() {
    return {...Object.fromEntries(Object.entries(controls).map(([key,c])=>[key,c.get_value() || ''])),...scopeOverrides,page:pageNumber,page_size:25,sort_by:sortBy,sort_order:sortOrder,completed_today:completedToday,issues_only:issuesOnly};
  }
  async function setScope(values) {
    muted = true;
    try { for (const [key,value] of Object.entries(values)) {
      if(value === '__unassigned__') scopeOverrides[key]=value; else delete scopeOverrides[key];
      await controls[key].set_value(value === '__unassigned__' ? '' : value);
    } }
    finally {muted = false;}
    pageNumber = 1; chips(); service.refresh();
  }
  function chips() {
    const target = root.find('.wob-filter-chips').empty();
    for (const def of filterDefs) {
      const value = scopeOverrides[def.fieldname] ? __('Unassigned') : controls[def.fieldname].get_value();
      if (value) $('<button class="wob-chip"></button>').text(`${def.label}: ${value} ×`).appendTo(target).on('click',()=>setScope({[def.fieldname]:''}));
    }
    if (completedToday || issuesOnly) $('<button class="wob-chip"></button>').text((completedToday ? __('Completed today') : __('Failed / Issues'))+' ×').appendTo(target).on('click',()=>{completedToday=0;issuesOnly=0;pageNumber=1;chips();service.refresh();});
  }
  root.find('.wob-clear').on('click',()=>{completedToday=0;issuesOnly=0;setScope(Object.fromEntries(filterDefs.map(def=>[def.fieldname,''])));});
  const kpis = [ ['Pending',__('Pending'),__('Awaiting preparation')],['Ready for Dispatch',__('Ready for Dispatch'),__('Packed and staged')],['Assigned',__('Assigned'),__('Allocated to drivers')],['Out for Delivery',__('Out for Delivery'),__('Currently in transit')],['today',__('Delivered Today'),__('Today, within filters')],['issues',__('Failed / Issues'),__('Failed and rescheduled')] ];
  function slug(status) { return String(status || '').toLowerCase().replace(/[^a-z0-9]+/g,'-'); }
  function badge(status) { return `<span class="wob-status status-${slug(status)}">${e(status || '—')}</span>`; }
  function renderKpis(value) {
    const grid = root.find('.wob-kpi-grid').empty();
    kpis.forEach(([key,label,description])=>{
      const count = !value ? null : key==='today' ? value.delivered_today : key==='issues' ? (value.counts?.Failed || 0)+(value.counts?.Rescheduled || 0) : value.counts?.[key] || 0;
      const selected = key==='today' ? completedToday : key==='issues' ? issuesOnly : controls.status.get_value()===key;
      $(`<button class="wob-kpi-card kpi-${slug(key)} ${selected?'selected':''}" aria-pressed="${!!selected}"><span>${e(label)}</span><strong class="${count===null?'wob-skeleton':''}">${count===null?'&nbsp;':e(count)}</strong><small>${e(description)}</small></button>`).appendTo(grid).on('click',()=>{
        completedToday = key==='today' && !selected ? 1 : 0; issuesOnly = key==='issues' && !selected ? 1 : 0;
        setScope({status:key==='today'||key==='issues'||selected?'':key});
      });
    });
  }
  function analytics(value) {
    const grid = root.find('.wob-analytics-grid').empty();
    [['by_zone','delivery_zone','delivery_zone',__('Deliveries by Zone')],['by_driver','assigned_driver','driver',__('Deliveries by Driver')],['by_company','company','company',__('Deliveries by Company')]].forEach(([key,field,filter,title])=>{
      const rows=value[key] || [], total=rows.reduce((sum,row)=>sum+Number(row.count || 0),0);
      const panel=$(`<section class="wob-panel"><h2>${e(title)} <small>${e(rows.length)} ${__('groups')}</small></h2><div class="wob-dist-list"></div></section>`).appendTo(grid), list=panel.find('.wob-dist-list');
      if (!rows.length) list.html(`<div class="wob-empty">${__('No deliveries in this scope')}</div>`);
      rows.forEach(row=>{
        const counts=row.counts || {}, percent=total?Math.round(Number(row.count || 0)/total*100):0;
        const item=$(`<button class="wob-dist-item"><span class="wob-dist-heading"><b>${e(row.label || row.driver_name || row[field] || __('Unassigned'))}</b><span>${e(row.active_count || 0)} ${__('active')} · ${e(percent)}%</span></span><span class="wob-stacked-bar">${Object.entries(counts).map(([status,n])=>`<i class="status-${slug(status)}" title="${e(status)}: ${e(n)}" style="width:${row.count?Math.max(0,Math.min(100,Number(n)/row.count*100)):0}%"></i>`).join('')}</span><span class="wob-dist-metrics">${Object.entries(counts).map(([status,n])=>`<span>${e(status)} <b>${e(n)}</b></span>`).join('')}<span>${__('Delivered today')} <b>${e(row.delivered_today || 0)}</b></span></span></button>`).appendTo(list);
        item.on('click',()=>setScope({[filter]:row[field] || '__unassigned__'}));
      });
    });
  }
  function actionButtons(order) {
    return `<button class="btn btn-xs btn-default" data-view="${e(order.name)}">${__('Quick View')}</button>`+(data?.can_manage ? actionsFor(order.delivery_status).map(action=>`<button class="btn btn-xs btn-default" data-action="${action}" data-id="${e(order.name)}">${e(labels[action])}</button>`).join(''):'');
  }
  function renderOrders(value) {
    const scroll=root.find('.wob-table-scroll'), left=scroll.scrollLeft(), top=scroll.scrollTop();
    const orders=value.orders || [], pagination=value.pagination || {page:1,total:orders.length,total_pages:1};
    pageNumber = pagination.page;
    const tbody=root.find('tbody').empty(), mobile=root.find('.wob-mobile-orders').empty();
    if (!orders.length) {tbody.html(`<tr><td colspan="9" class="wob-empty">${__('No delivery tasks match these filters.')}</td></tr>`);mobile.html(`<div class="wob-empty">${__('No delivery tasks match these filters.')}</div>`);}
    orders.forEach(order=>{
      const link=`/app/wob-delivery-order/${encodeURIComponent(order.name)}`, name=`<a class="wob-order-link" href="${link}">${e(order.name)}</a>`, highlight=changes.has(order.name)?'wob-changed':'';
      const date=order.scheduled_delivery_date ? frappe.datetime.str_to_user(order.scheduled_delivery_date) : '—';
      $(`<tr class="${highlight}"><td>${name}</td><td>${e(order.company || '—')}</td><td>${e(order.customer_name || order.customer || '—')}</td><td>${e(order.zone_name || order.delivery_zone || '—')}</td><td>${e(order.driver_name || order.assigned_driver || __('Unassigned'))}</td><td>${badge(order.delivery_status)}</td><td>${e(date)}</td><td>${e(order.payment_type || '—')}</td><td><div class="wob-row-actions">${actionButtons(order)}</div></td></tr>`).appendTo(tbody);
      $(`<article class="wob-order-mobile ${highlight}"><header>${name}${badge(order.delivery_status)}</header><h3>${e(order.customer_name || order.customer || '—')}</h3><p>${e(order.company || '—')} · ${e(order.zone_name || order.delivery_zone || '—')}</p><p>${e(order.driver_name || order.assigned_driver || __('Unassigned'))} · ${e(date)}</p><p>${e(order.payment_type || '—')}</p><div class="wob-row-actions">${actionButtons(order)}</div></article>`).appendTo(mobile);
    });
    root.find('.wob-total').text(`${pagination.total} ${__('tasks in current scope')}`);
    root.find('.wob-page-label').text(`${__('Page')} ${pagination.page} / ${Math.max(1,pagination.total_pages)}`);
    root.find('.wob-prev').prop('disabled',pagination.page<=1);root.find('.wob-next').prop('disabled',pagination.page>=pagination.total_pages);
    scroll.scrollLeft(left).scrollTop(top);
  }
  root.on('click','[data-view]',function(){showDetails($(this).attr('data-view'));});
  root.on('click','[data-action]',function(){const name=$(this).attr('data-id'), action=$(this).attr('data-action');const order=data?.orders?.find(row=>row.name===name);if(order) perform(order,action);});
  root.on('click','[data-sort]',function(){const key=$(this).attr('data-sort');sortOrder=sortBy===key&&sortOrder==='asc'?'desc':'asc';sortBy=key;pageNumber=1;service.refresh();});
  root.find('.wob-prev').on('click',()=>{pageNumber=Math.max(1,pageNumber-1);service.refresh();});
  root.find('.wob-next').on('click',()=>{pageNumber++;service.refresh();});
  const service=createSyncService({args,fetch:async params=>{lastRequest=Date.now();const r=await frappe.call({method:'wob_delivery.api.get_dashboard',args:params});return r.message;},loading:()=>{root.attr('aria-busy','true');},render:value=>{
    if (!value) throw new Error(__('Dashboard returned no data.'));
    data=value;root.attr('aria-busy','false');root.find('.wob-error').prop('hidden',true);renderKpis(value);analytics(value);renderOrders(value);clock();
    root.find('.wob-last-sync').text(`${__('Last synced')} ${new Date().toLocaleTimeString()}`);
    for(const [id,time] of changes) if(Date.now()-time>5000) changes.delete(id);
    if(detail) refreshDetails();
  },error:()=>{root.attr('aria-busy','false');const target=root.find('.wob-error').prop('hidden',false).empty();$('<span></span>').text(__('Unable to sync delivery data. Displayed values may be stale. ')).appendTo(target);$('<button class="btn btn-sm btn-default"></button>').text(__('Retry')).appendTo(target).on('click',()=>service.refresh());}});
  async function showDetails(name) {
    if(detail) detail.dialog.hide();
    const dialog=new frappe.ui.Dialog({title:name,fields:[{fieldname:'content',fieldtype:'HTML'}]});
    detail={name,dialog};dialog.$wrapper.on('hidden.bs.modal',()=>{if(detail?.dialog===dialog){detail=null;detailSequence++;}});dialog.show();await refreshDetails();
  }
  async function refreshDetails() {
    if(!detail) return;const current=detail, sequence=++detailSequence;
    try {
      const r=await frappe.call({method:'wob_delivery.dashboard.get_task_details',args:{name:current.name}});
      if(detail!==current||sequence!==detailSequence) return;
      const value=r.message, order=value.order, content=current.dialog.fields_dict.content.$wrapper, scroll=content.scrollTop();
      content.html(`<div class="wob-detail">${badge(order.delivery_status)}<h3>${e(order.customer_name || order.customer || '—')}</h3><p>${e(order.company || '—')} · ${e(order.zone_name || order.delivery_zone || '—')}</p><p>${e(order.driver_name || order.assigned_driver || __('Unassigned'))}</p><a href="/app/wob-delivery-order/${encodeURIComponent(order.name)}">${__('Open full Delivery Order')} ↗</a><h4>${__('Recorded timeline')}</h4><ol class="wob-timeline">${(value.timeline || []).map(item=>`<li><b>${e(item.previous_status ? item.previous_status+' → '+item.new_status : item.new_status || __('Updated'))}</b><span>${e(item.changed_at ? frappe.datetime.str_to_user(item.changed_at) : '')} ${e(item.changed_by || '')}${item.new_driver ? ' · '+e(item.new_driver) : ''}</span>${item.reason?`<p>${e(item.reason)}</p>`:''}</li>`).join('') || `<li>${__('No recorded history available.')}</li>`}</ol><div class="wob-row-actions"></div></div>`);
      if(data?.can_manage) actionsFor(order.delivery_status).forEach(action=>$('<button class="btn btn-default btn-sm"></button>').text(labels[action]).appendTo(content.find('.wob-row-actions')).on('click',()=>perform(order,action)));
      content.scrollTop(scroll);
    } catch(error) {if(detail===current&&sequence===detailSequence) current.dialog.fields_dict.content.$wrapper.text(__('Unable to load delivery details. Close and retry.'));}
  }
  async function perform(order,action) {
    if(!data?.can_manage || !actionsFor(order.delivery_status).includes(action)) return;
    let dialog;
    const submit=async values=>{
      dialog.get_primary_btn().prop('disabled',true);
      try {await frappe.call({method:'wob_delivery.dashboard.perform_action',args:{name:order.name,action,...values}});dialog.hide();frappe.show_alert({message:__('Delivery updated'),indicator:'green'});service.refresh(true);}
      finally {dialog.get_primary_btn().prop('disabled',false);}
    };
    if(action==='assign') {
      const r=await frappe.call({method:'wob_delivery.api.get_driver_recommendations',args:{company:order.company,delivery_zone:order.delivery_zone}}), rows=r.message || [], eligible=rows.filter(row=>row.can_assign);
      dialog=new frappe.ui.Dialog({title:__('Assign eligible driver'),fields:[{fieldname:'workload',fieldtype:'HTML',options:`<div class="wob-driver-options">${rows.map(row=>`<p><b>${e(row.driver_name || row.driver)}</b> · ${e(row.availability_status)} · ${e(row.active_deliveries)} ${__('active')} · ${e(row.assignment_type || '')}${!row.can_assign?' · '+__('Unavailable'):''}</p>`).join('') || e(__('No eligible drivers mapped to this zone.'))}</div>`},{fieldname:'driver',label:__('Driver'),fieldtype:'Select',reqd:1,options:eligible.map(row=>({label:`${row.driver_name || row.driver} · ${row.active_deliveries} ${__('active')}`,value:row.driver}))}],primary_action_label:__('Assign Driver'),primary_action:submit});
      dialog.show();if(!eligible.length)dialog.get_primary_btn().prop('disabled',true);
    } else {
      dialog=new frappe.ui.Dialog({title:labels[action],fields:action==='failed'?[{fieldname:'reason',label:__('Failure reason'),fieldtype:'Small Text',reqd:1}]:[{fieldname:'confirmation',fieldtype:'HTML',options:`<p>${e(labels[action])}: <b>${e(order.name)}</b>?</p>`}],primary_action_label:labels[action],primary_action:submit});dialog.show();
    }
  }
  function clock() {
    let date;
    try {const now=new Date(), timezone=data?.timezone || frappe.boot.time_zone?.system;root.find('.wob-clock').text(new Intl.DateTimeFormat(undefined,{dateStyle:'full',timeStyle:'medium',...(timezone?{timeZone:timezone}:{})}).format(now));date=new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',...(timezone?{timeZone:timezone}:{})}).format(now);}
    catch(error) {root.find('.wob-clock').text(new Date().toLocaleString());date=frappe.datetime.get_today();}
    if(lastDate&&lastDate!==date)service.refresh(true);lastDate=date;
  }
  function connection() {
    const connected=!!frappe.realtime.socket?.connected, offline=navigator.onLine===false;
    root.find('.wob-connection').attr('class',`wob-connection ${connected?'connected':offline?'offline':'reconnecting'}`).text(connected?__('Live — Connected'):offline?__('Offline'):__('Reconnecting'));
    return connected;
  }
  function onConnect() {retryDelay=5000;retryAfter=0;connection();if(visible&&!document.hidden)service.refresh(true);}
  function onDisconnect() {connection();}
  function eventHandler(event) {
    if(!visible || !event?.delivery_id) return;
    const key=event.event_id || `${event.delivery_id}:${event.revision || event.action}`;
    if(seen.has(key))return;seen.add(key);if(seen.size>500)seen.delete(seen.values().next().value);
    changes.set(event.delivery_id,Date.now());service.changed();
    notifications.unshift({name:event.delivery_id,action:event.action || __('updated')});notifications.splice(20);
    const target=root.find('.wob-notifications').empty();notifications.forEach(item=>$('<button class="wob-notification"></button>').text(`${item.name} · ${item.action}`).appendTo(target).on('click',()=>showDetails(item.name)));root.find('.wob-notification-count').text(notifications.length);
  }
  root.find('.wob-notifications-toggle').on('click',()=>{const target=root.find('.wob-notifications');target.prop('hidden',!target.prop('hidden'));});
  function reconcile() {
    if(!visible||document.hidden)return;
    const connected=connection(), now=Date.now();clock();
    if(!connected&&navigator.onLine!==false&&now>=retryAfter) {frappe.realtime.socket?.connect();retryAfter=now+retryDelay;retryDelay=Math.min(60000,retryDelay*2);}
    if(now-lastRequest>=(connected?60000:30000)) service.refresh(true);
  }
  function wake() {if(!visible)return;if(document.hidden){service.stop();}else{service.start();connection();}}
  function focus() {if(visible&&!document.hidden){service.start();service.refresh(true);connection();}}
  function show() {
    if(visible)return;visible=true;frappe.realtime.on('wob_delivery_changed',eventHandler);socket=frappe.realtime.socket;
    socket?.on('connect',onConnect);socket?.on('disconnect',onDisconnect);socket?.on('connect_error',onDisconnect);
    if(configureDevSocket(socket,{dev_server:window.dev_server,hostname:window.location.hostname,sitename:frappe.boot.sitename})) {socket.disconnect();socket.connect();}
    document.addEventListener('visibilitychange',wake);window.addEventListener('focus',focus);window.addEventListener('online',focus);window.addEventListener('offline',onDisconnect);
    heartbeat=setInterval(reconcile,5000);clockTimer=setInterval(clock,1000);connection();clock();if(!document.hidden)service.start();
  }
  function hide() {
    if(!visible)return;visible=false;service.stop();clearInterval(heartbeat);clearInterval(clockTimer);clearTimeout(searchTimer);
    frappe.realtime.off('wob_delivery_changed',eventHandler);socket?.off('connect',onConnect);socket?.off('disconnect',onDisconnect);socket?.off('connect_error',onDisconnect);
    document.removeEventListener('visibilitychange',wake);window.removeEventListener('focus',focus);window.removeEventListener('online',focus);window.removeEventListener('offline',onDisconnect);
  }
  wrapper.wobDashboard={show,hide,destroy(){hide();detail?.dialog.hide();detail=null;root.remove();$(wrapper).off('.wobDelivery');}};
  $(wrapper).off('.wobDelivery').on('show.wobDelivery',show).on('hide.wobDelivery',hide);
  page.set_primary_action(__('New Delivery Task'),()=>frappe.new_doc('WOB Delivery Order',{company:controls.company.get_value(),scheduled_delivery_date:frappe.datetime.get_today()}),'add');
  page.add_inner_button(__('From Sales Document'), async () => {
    const company = controls.company.get_value();
    const dialog = new frappe.ui.Dialog({
      title: __('Select Document for Delivery'),
      fields: [
        {
          fieldname: 'source_type',
          label: __('Document Type'),
          fieldtype: 'Select',
          options: 'Sales Invoice\nSales Order\nDelivery Note',
          reqd: 1
        },
        {
          fieldname: 'results_html',
          fieldtype: 'HTML'
        }
      ],
      primary_action_label: __('Search Eligible Documents'),
      primary_action: async values => {
        dialog.fields_dict.results_html.$wrapper.html(`
          <div class="text-center p-3 text-muted">
            <span class="spinner-border spinner-border-sm"></span> ${__('Searching...')}
          </div>
        `);
        const r = await frappe.call({
          method: 'wob_delivery.api.get_eligible_orders',
          args: { company, source_type: values.source_type }
        });
        const target = dialog.fields_dict.results_html.$wrapper.empty();
        const list = r.message || [];
        if (!list.length) {
          target.html(`
            <div class="alert alert-info text-center mt-2 mb-0">
              ${__('No eligible submitted documents found for the selected filters.')}
            </div>
          `);
          return;
        }

        const container = $('<div style="max-height: 320px; overflow-y: auto;" class="mt-2"></div>').appendTo(target);
        list.forEach(doc => {
          $(`
            <div class="d-flex align-items-center justify-content-between p-2 mb-2 border rounded" style="background: var(--bg-color);">
              <div>
                <strong>${frappe.utils.escape_html(doc.name)}</strong> · <span class="text-muted">${frappe.utils.escape_html(doc.customer || '')}</span>
                <div class="small text-muted">${frappe.utils.escape_html(doc.company || '')}</div>
                <div class="small text-muted">${frappe.utils.escape_html(doc.currency || '')} ${frappe.utils.escape_html(String(format_currency(doc.grand_total, doc.currency)))}</div>
              </div>
              <button class="btn btn-xs btn-primary wob-btn-pick-doc">
                ${__('Create Delivery')}
              </button>
            </div>
          `)
            .appendTo(container)
            .find('.wob-btn-pick-doc')
            .on('click', () => {
              dialog.hide();
              const keyMap = {
                'Sales Invoice': 'sales_invoice',
                'Sales Order': 'sales_order',
                'Delivery Note': 'delivery_note'
              };
              frappe.new_doc('WOB Delivery Order', {
                company: doc.company,
                [keyMap[values.source_type]]: doc.name,
                scheduled_delivery_date: frappe.datetime.get_today()
              });
            });
        });
      }
    });

    dialog.show();
    // Set Select values explicitly: FieldGroup lowercases string defaults.
    await dialog.set_value('source_type', 'Sales Order');
    dialog.get_primary_btn().trigger('click');
  });

  page.add_inner_button(__('Delivery Register'), () => {
    frappe.set_route('query-report', 'WOB Delivery Register');
  });

  if (frappe.session.user === 'Administrator' || frappe.user.has_role('System Manager') || frappe.user.has_role('WOB Delivery Administrator')) {
    page.add_inner_button(__('Bank Collection Setup'), () => {
      let setup;
      const accountFilters = () => ({company:setup.get_value('company'),account_type:'Bank',is_group:0,disabled:0});
      setup = new frappe.ui.Dialog({
        title:__('Bank Collection Setup'),
        fields:[
          {fieldtype:'HTML',options:`<p>${__('Name the bank as drivers should see it. Link an existing Bank ledger account, or create one under your company bank account group. Each bank can have its own payment method.')}</p>`},
          {fieldname:'company',label:__('Company'),fieldtype:'Link',options:'Company',reqd:1,change:async()=>{
            await setup.set_value('account','');await setup.set_value('parent_account','');
            const company=setup.get_value('company');if(!company)return;
            const result=await frappe.db.get_value('Account',{company,account_name:'Bank Accounts',is_group:1},'name');
            if(setup.get_value('company')===company&&result.message?.name)await setup.set_value('parent_account',result.message.name);
          }},
          {fieldname:'bank_name',label:__('Bank / Payment Method Name'),fieldtype:'Data',reqd:1,description:__('For example: QNB Bank Transfer. This name is shown in the driver app.')},
          {fieldname:'create_account',label:__('Create a new Bank ledger account'),fieldtype:'Check'},
          {fieldname:'account',label:__('Receiving Bank Account'),fieldtype:'Link',options:'Account',depends_on:'eval:!doc.create_account',mandatory_depends_on:'eval:!doc.create_account',get_query:()=>({filters:accountFilters()})},
          {fieldname:'parent_account',label:__('Bank Account Group'),fieldtype:'Link',options:'Account',depends_on:'eval:doc.create_account',mandatory_depends_on:'eval:doc.create_account',get_query:()=>({filters:{company:setup.get_value('company'),is_group:1,root_type:'Asset',disabled:0}})},
          {fieldtype:'HTML',options:`<p class="text-muted">${__('The receiving account must use the company currency. Bank receipts require a transfer reference and confirmation that funds were received.')}</p>`}
        ],
        primary_action_label:__('Save Bank for Collections'),
        primary_action:async values=>{
          setup.get_primary_btn().prop('disabled',true);
          try {
            const response=await frappe.call({method:'wob_delivery.bank_setup.save_bank_collection',args:{company:values.company,bank_name:values.bank_name,account:values.create_account?null:values.account,parent_account:values.create_account?values.parent_account:null}});
            setup.hide();
            frappe.msgprint({title:__('Bank Collection Ready'),indicator:'green',message:__('Bank {0} is available in driver Payment Collection. Receiving account: {1}.',[e(response.message.mode_of_payment),e(response.message.account)])});
          } finally {setup.get_primary_btn().prop('disabled',false);}
        }
      });
      setup.set_secondary_action_label(__('Manage Saved Banks'));
      setup.set_secondary_action(()=>{setup.hide();frappe.set_route('List','Mode of Payment',{type:'Bank'});});
      setup.show();
      if(controls.company.get_value())setup.set_value('company',controls.company.get_value());
    });
  }

  page.add_inner_button(__('Refresh Now'),()=>service.refresh(true));
  renderKpis(null);root.find('tbody').html('<tr><td colspan="9"><div class="wob-skeleton wob-table-skeleton"></div></td></tr>');show();
};
frappe.pages['wob-delivery-dashboard'].on_page_show = wrapper => wrapper.wobDashboard?.show();
}
