frappe.query_reports['WOB Delivery Register']={filters:[
 {fieldname:'company',label:__('Company'),fieldtype:'Link',options:'Company'},
 {fieldname:'delivery_zone',label:__('Zone'),fieldtype:'Link',options:'WOB Delivery Zone'},
 {fieldname:'driver',label:__('Driver'),fieldtype:'Link',options:'Driver'},
 {fieldname:'from_date',label:__('From Date'),fieldtype:'Date'},
 {fieldname:'to_date',label:__('To Date'),fieldtype:'Date'},
 {fieldname:'status',label:__('Status'),fieldtype:'Select',options:'\nPending\nReady for Dispatch\nAssigned\nOut for Delivery\nDelivered\nFailed\nRescheduled\nCancelled'}
]};
