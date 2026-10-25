app_name = "wob_delivery"
app_title = "WOB Delivery"
app_publisher = "Worlds of Birds"
app_description = "Delivery Management for Worlds of Birds"
app_email = "bijay@stsqa.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "wob_delivery",
		"logo": "/assets/wob_delivery/images/wob_delivery-logo.svg",
		"title": "WOB Delivery",
		"route": "/desk/wob-delivery-dashboard",
		"sequence_id": 3,
	}
]

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `wob_delivery/dock/wob_delivery/wob_delivery.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/wob_delivery/css/wob_delivery.css"
# app_include_js = "/assets/wob_delivery/js/wob_delivery.js"

# include js, css files in header of web template
# web_include_css = "/assets/wob_delivery/css/wob_delivery.css"
# web_include_js = "/assets/wob_delivery/js/wob_delivery.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "wob_delivery/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_kanban_js = {"doctype" : "public/js/doctype_kanban.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "wob_delivery/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "wob_delivery.utils.jinja_methods",
# 	"filters": "wob_delivery.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "wob_delivery.install.before_install"
# after_install = "wob_delivery.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "wob_delivery.uninstall.before_uninstall"
# after_uninstall = "wob_delivery.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "wob_delivery.utils.before_app_install"
# after_app_install = "wob_delivery.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "wob_delivery.utils.before_app_uninstall"
# after_app_uninstall = "wob_delivery.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "wob_delivery.build.after_build"

# To hook into the build process of other apps
# The list of apps being built is passed as an argument

# after_app_build = "wob_delivery.build.after_app_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "wob_delivery.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["wob_delivery.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"wob_delivery.tasks.all"
# 	],
# 	"daily": [
# 		"wob_delivery.tasks.daily"
# 	],
# 	"hourly": [
# 		"wob_delivery.tasks.hourly"
# 	],
# 	"weekly": [
# 		"wob_delivery.tasks.weekly"
# 	],
# 	"monthly": [
# 		"wob_delivery.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "wob_delivery.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "wob_delivery.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "wob_delivery.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "wob_delivery.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["wob_delivery.utils.before_request"]
# after_request = ["wob_delivery.utils.after_request"]

# Job Events
# ----------
# before_job = ["wob_delivery.utils.before_job"]
# after_job = ["wob_delivery.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"wob_delivery.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


# Phase 1: native ERPNext delivery tasks, without stock/payment posting.
required_apps = ["erpnext"]
doctype_js = {"Sales Order": "public/js/sales_order.js"}
app_include_css = ["/assets/wob_delivery/css/wob_delivery_order.css"]
after_install = "wob_delivery.setup.after_install"
after_migrate = "wob_delivery.setup.after_migrate"
permission_query_conditions = {
 "WOB Delivery Order": "wob_delivery.permissions.order_query",
 "WOB Delivery Zone": "wob_delivery.permissions.zone_query",
 "WOB Driver Zone Assignment": "wob_delivery.permissions.assignment_query",
 "WOB Delivery Assignment History": "wob_delivery.permissions.history_query",
}
has_permission = {
 "WOB Delivery Order": "wob_delivery.permissions.order_permission",
 "WOB Delivery Zone": "wob_delivery.permissions.staff_permission",
 "WOB Driver Zone Assignment": "wob_delivery.permissions.staff_permission",
 "WOB Delivery Assignment History": "wob_delivery.permissions.staff_permission",
}

# Only linked collection receipts emit delivery invalidations; no financial payloads.
doc_events = {
 "Payment Entry": {
  "on_submit": "wob_delivery.live.payment_changed",
  "on_cancel": "wob_delivery.live.payment_changed",
 }
}
