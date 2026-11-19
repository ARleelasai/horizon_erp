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

# ---------------------------------------------------------------- doc events
doc_events = {
	"*": {
		"before_validate": "horizon_erp.overrides.dimensions.set_branch",
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
