app_name = "horizon_erp"
app_title = "Horizon ERP"
app_publisher = "Leela Sai"
app_description = "Horizon Manufacturing Ltd ERPNext implementation: masters, workflows, validations, reports, API and seed data"
app_email = "ar.leelasai@dford.co.in"
app_license = "mit"

required_apps = ["erpnext", "hrms", "india_compliance"]

# ---------------------------------------------------------------- install
after_install = "horizon_erp.setup.install.after_install"
after_migrate = "horizon_erp.setup.install.after_migrate"

# ---------------------------------------------------------------- client scripts
doctype_js = {
	"Quotation": "public/js/hml_selling.js",
	"Sales Order": "public/js/hml_selling.js",
	"Delivery Note": "public/js/hml_delivery_note.js",
}

# ---------------------------------------------------------------- class overrides
override_doctype_class = {
	"Purchase Receipt": "horizon_erp.overrides.purchase_receipt.HMLPurchaseReceipt",
}

# ---------------------------------------------------------------- doc events
doc_events = {
	"*": {
		"before_validate": "horizon_erp.overrides.dimensions.set_branch",
	},
	"Lead": {"validate": "horizon_erp.overrides.selling.validate_lead"},
	"Opportunity": {"validate": "horizon_erp.overrides.selling.validate_opportunity"},
	"Quotation": {
		"validate": "horizon_erp.overrides.selling.validate_quotation",
		"on_update": "horizon_erp.overrides.selling.on_update_quotation",
		"before_submit": "horizon_erp.overrides.selling.before_submit_quotation",
		"on_submit": "horizon_erp.overrides.selling.on_submit_quotation",
	},
	"Sales Order": {
		"validate": "horizon_erp.overrides.selling.validate_sales_order",
		"before_submit": "horizon_erp.overrides.selling.before_submit_sales_order",
	},
	"Delivery Note": {
		"before_validate": "horizon_erp.overrides.selling.before_validate_delivery_note",
		"validate": "horizon_erp.overrides.selling.validate_delivery_note",
		"before_submit": "horizon_erp.overrides.selling.before_submit_delivery_note",
		"on_submit": "horizon_erp.overrides.selling.on_submit_delivery_note",
	},
	"Sales Invoice": {
		"validate": "horizon_erp.overrides.selling.validate_sales_invoice",
	},
	"Stock Reconciliation": {
		"before_validate": "horizon_erp.tasks.inventory.before_stock_reco_validate",
		"on_submit": "horizon_erp.tasks.inventory.on_stock_reco_submit",
	},
}

# ---------------------------------------------------------------- scheduler
scheduler_events = {
	"weekly": [
		"horizon_erp.tasks.inventory.create_cycle_count_drafts",
	],
}
