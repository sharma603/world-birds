import frappe
from wob_delivery.api import delivery_filters, ORDER_FIELDS

def execute(filters=None):
 filters=frappe._dict(filters or {})
 query=delivery_filters(filters.company,filters.delivery_zone,filters.driver,filters.from_date,filters.to_date,filters.status)
 columns=[{'fieldname':key,'label':label,'fieldtype':kind,'options':options,'width':width} for key,label,kind,options,width in [
 ('name','Delivery Order','Link','WOB Delivery Order',180),('company','Company','Link','Company',150),('customer','Customer','Link','Customer',160),('delivery_zone','Zone','Link','WOB Delivery Zone',140),('assigned_driver','Driver','Link','Driver',140),('delivery_status','Status','Data',None,140),('scheduled_delivery_date','Scheduled Date','Date',None,120),('currency','Currency','Link','Currency',90),('amount_to_collect','Amount to Collect','Currency','currency',140)]]
 return columns,frappe.get_list('WOB Delivery Order',filters=query,fields=ORDER_FIELDS,order_by='scheduled_delivery_date asc',limit_page_length=0)
