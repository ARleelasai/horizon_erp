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
	"Work Order": "public/js/hml_manufacturing.js",
	"Production Plan": "public/js/hml_manufacturing.js",
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
		"on_submit": "horizon_erp.manufacturing.masters.on_submit_sales_order",
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
	"Purchase Order": {
		"validate": "horizon_erp.overrides.buying.validate_purchase_order",
		"before_save": "horizon_erp.overrides.buying.before_save_purchase_order",
		"on_update": "horizon_erp.overrides.buying.on_update_purchase_order",
		"on_submit": "horizon_erp.overrides.buying.on_submit_purchase_order",
		"on_cancel": "horizon_erp.overrides.buying.on_cancel_purchase_order",
	},
	"Purchase Receipt": {
		"before_validate": "horizon_erp.overrides.buying.before_validate_purchase_receipt",
		"validate": "horizon_erp.overrides.buying.validate_blacklisted_without_po",
		"on_submit": "horizon_erp.overrides.buying.on_submit_purchase_receipt",
	},
	"Purchase Invoice": {
		"before_validate": "horizon_erp.overrides.buying.apply_rcm_for_unregistered",
		"validate": [
			"horizon_erp.overrides.buying.validate_blacklisted_without_po",
			"horizon_erp.strategy.migration.validate_purchase_invoice_po",
		],
	},
	"Payment Entry": {"validate": "horizon_erp.accounts.bank.validate_bank_lock"},
	"Journal Entry": {"validate": "horizon_erp.accounts.bank.validate_bank_lock"},

	"Quality Inspection": {
		"validate": "horizon_erp.overrides.buying.validate_quality_inspection",
		"before_submit": [
			"horizon_erp.overrides.buying.before_submit_quality_inspection",
			"horizon_erp.manufacturing.quality.before_submit_qi_photo",
		],
		"on_submit": "horizon_erp.manufacturing.quality.on_submit_quality_inspection",
	},
	"BOM": {"validate": "horizon_erp.manufacturing.masters.validate_bom"},
	"Workstation": {"validate": "horizon_erp.manufacturing.masters.validate_workstation"},
	"Work Order": {"validate": "horizon_erp.manufacturing.capacity.validate_work_order"},
	"Job Card": {"before_submit": "horizon_erp.manufacturing.quality.before_submit_job_card"},
	"Stock Entry": {"before_submit": "horizon_erp.manufacturing.audit.validate_manufacture_entry"},
	"Project": {"validate": "horizon_erp.overrides.projects.update_project_costing"},
	"Task": {
		"validate": "horizon_erp.overrides.projects.validate_task",
		"on_update": "horizon_erp.overrides.projects.on_update_task",
	},
	"Timesheet": {"validate": "horizon_erp.overrides.projects.validate_timesheet"},
	"Employee": {"validate": "horizon_erp.overrides.hr.validate_employee"},
	"Leave Application": {"validate": "horizon_erp.overrides.hr.validate_leave_application"},
	"Salary Slip": {"before_validate": "horizon_erp.overrides.hr.before_validate_salary_slip"},
	"Stock Reconciliation": {
		"before_validate": "horizon_erp.tasks.inventory.before_stock_reco_validate",
		"on_submit": "horizon_erp.tasks.inventory.on_stock_reco_submit",
	},
}

# ---------------------------------------------------------------- scheduler
scheduler_events = {
	"cron": {
		"0 */6 * * *": ["horizon_erp.tasks.approvals.send_approval_reminders"],
		"0 18 * * *": ["horizon_erp.tasks.jobs.daily_summary"],
		"0 9 1 * *": ["horizon_erp.tasks.jobs.monthly_budget"],
	},
	"hourly": [
		"horizon_erp.tasks.approvals.escalate_stale_approvals",
		# reorder requests + inventory accuracy, logged; also retries failed jobs once
		"horizon_erp.tasks.jobs.hourly",
	],
	"daily": [
		"horizon_erp.tasks.reorder.recalculate_reorder_levels",
		"horizon_erp.horizon_erp.doctype.corrective_action.corrective_action.mark_overdue",
		"horizon_erp.overrides.projects.refresh_all_projects",
		"horizon_erp.strategy.conflicts.daily_scan",
		"horizon_erp.accounts.budget.alert_cost_centers_over_90",
	],
	"weekly": [
		"horizon_erp.tasks.inventory.create_cycle_count_drafts",
	],
}

# ---------------------------------------------------------------- API
# /api/method/get_inventory_snapshot (short path required by the Delhi DC integration)
override_whitelisted_methods = {
	"get_inventory_snapshot": "horizon_erp.api.inventory.get_inventory_snapshot",
}

# ---------------------------------------------------------------- printing
jinja = {
	"methods": [
		"horizon_erp.printing.hml_customer_outstanding",
		"horizon_erp.printing.hml_payment_due_date",
		"horizon_erp.printing.hml_total_discount_pct",
		"horizon_erp.printing.hml_similar_in_stock",
		"horizon_erp.printing.hml_company_registration",
	],
}
