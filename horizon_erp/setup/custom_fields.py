"""Custom fields owned by horizon_erp.

Applied idempotently on every `bench migrate` (hooks.after_migrate), so the
definitions here are the source of truth. All fieldnames are prefixed `hml_`
to stay clear of the custom_* fields other apps on this site add.
"""

ITEM_FIELDS = [
	{
		"fieldname": "hml_planning_tab",
		"label": "Horizon Planning",
		"fieldtype": "Tab Break",
		"insert_after": "total_projected_qty",
	},
	{
		"fieldname": "hml_criticality",
		"label": "Criticality",
		"fieldtype": "Select",
		"options": "\nA - Critical\nB - Important\nC - Standard",
		"default": "C - Standard",
		"insert_after": "hml_planning_tab",
		"description": "Drives the safety-stock factor in the reorder formula (A 2.0, B 1.5, C 1.0 × lead-time usage spread).",
	},
	{
		"fieldname": "hml_demand_pattern",
		"label": "Demand Pattern",
		"fieldtype": "Select",
		"options": "\nStable\nSeasonal - Q4 Spike\nIrregular",
		"default": "Stable",
		"insert_after": "hml_criticality",
	},
	{
		"fieldname": "hml_avg_daily_usage",
		"label": "Average Daily Usage",
		"fieldtype": "Float",
		"insert_after": "hml_demand_pattern",
		"read_only": 1,
		"description": "Recalculated nightly from the last 90 days of stock consumption and sales.",
	},
	{
		"fieldname": "hml_safety_stock_qty",
		"label": "Safety Stock (calculated)",
		"fieldtype": "Float",
		"insert_after": "hml_avg_daily_usage",
		"read_only": 1,
	},
	{
		"fieldname": "hml_reorder_point",
		"label": "Reorder Point (calculated)",
		"fieldtype": "Float",
		"insert_after": "hml_safety_stock_qty",
		"read_only": 1,
	},
	{
		"fieldname": "hml_col_planning",
		"fieldtype": "Column Break",
		"insert_after": "hml_reorder_point",
	},
	{
		"fieldname": "hml_abc_class",
		"label": "ABC Class (cycle count)",
		"fieldtype": "Select",
		"options": "\nA\nB\nC",
		"default": "C",
		"insert_after": "hml_col_planning",
		"description": "A counted every 30 days, B every 60, C every 90.",
	},
	{
		"fieldname": "hml_last_counted_on",
		"label": "Last Counted On",
		"fieldtype": "Date",
		"insert_after": "hml_abc_class",
		"read_only": 1,
	},
	{
		"fieldname": "hml_mfg_section",
		"label": "Manufacturing",
		"fieldtype": "Section Break",
		"insert_after": "hml_last_counted_on",
	},
	{
		"fieldname": "hml_machine_hours_per_unit",
		"label": "Machine Hours per Unit",
		"fieldtype": "Float",
		"insert_after": "hml_mfg_section",
		"description": "Line hours one unit consumes. Used by the Work Order capacity check.",
	},
	{
		"fieldname": "hml_eligible_lines",
		"label": "Eligible Production Lines",
		"fieldtype": "Select",
		"options": "\nAny\nLine A\nLine B",
		"default": "Any",
		"insert_after": "hml_machine_hours_per_unit",
	},
	{
		"fieldname": "hml_col_mfg",
		"fieldtype": "Column Break",
		"insert_after": "hml_eligible_lines",
	},
	{
		"fieldname": "hml_mfg_lead_time_days",
		"label": "Manufacturing Lead Time (days)",
		"fieldtype": "Int",
		"insert_after": "hml_col_mfg",
		"description": "Working days from Work Order release to finished goods. Feeds quotation delivery dates.",
	},
	{
		"fieldname": "hml_make_to_stock",
		"label": "Make to Stock",
		"fieldtype": "Check",
		"insert_after": "hml_mfg_lead_time_days",
		"description": "Ticked: a submitted Sales Order auto-creates a draft Work Order. Unticked: make-to-order, planner creates it.",
	},
]

SUPPLIER_FIELDS = [
	{
		"fieldname": "hml_quality_section",
		"label": "Quality Status",
		"fieldtype": "Section Break",
		"insert_after": "is_frozen",
		"collapsible": 0,
	},
	{
		"fieldname": "hml_is_blacklisted",
		"label": "Blacklisted",
		"fieldtype": "Check",
		"insert_after": "hml_quality_section",
		"description": "Blocks Purchase Orders unless an override reason is recorded; overrides escalate to the Finance Director.",
	},
	{
		"fieldname": "hml_blacklisted_on",
		"label": "Blacklisted On",
		"fieldtype": "Date",
		"insert_after": "hml_is_blacklisted",
		"depends_on": "hml_is_blacklisted",
	},
	{
		"fieldname": "hml_blacklist_reason",
		"label": "Blacklist Reason",
		"fieldtype": "Small Text",
		"insert_after": "hml_blacklisted_on",
		"depends_on": "hml_is_blacklisted",
		"mandatory_depends_on": "hml_is_blacklisted",
	},
]


STOCK_RECO_FIELDS = [
	{
		"fieldname": "hml_cycle_count_warehouse",
		"label": "Cycle Count Warehouse",
		"fieldtype": "Link",
		"options": "Warehouse",
		"insert_after": "purpose",
		"read_only": 1,
		"description": "Set when the weekly cycle-count job created this draft.",
	},
]


def _pricing_fields(after):
	"""Discount-control fields shared by Quotation and Sales Order."""
	return [
		{"fieldname": "hml_pricing_section", "label": "Pricing Control", "fieldtype": "Section Break", "insert_after": after, "collapsible": 0},
		{"fieldname": "hml_list_value", "label": "Value at Price List", "fieldtype": "Currency", "options": "currency", "read_only": 1, "insert_after": "hml_pricing_section"},
		{"fieldname": "hml_effective_discount_pct", "label": "Effective Discount %", "fieldtype": "Percent", "read_only": 1, "insert_after": "hml_list_value",
			"description": "Total discount vs price list (pricing rules + manual + header discount). Above 15 % needs Sales Manager approval."},
		{"fieldname": "hml_manual_discount_pct", "label": "Manual Discount % (beyond pricing rules)", "fieldtype": "Percent", "read_only": 1, "insert_after": "hml_effective_discount_pct"},
		{"fieldname": "hml_col_pricing", "fieldtype": "Column Break", "insert_after": "hml_manual_discount_pct"},
		{"fieldname": "hml_needs_discount_approval", "label": "Needs Discount Approval", "fieldtype": "Check", "read_only": 1, "insert_after": "hml_col_pricing"},
		{"fieldname": "hml_below_cost", "label": "Priced Below Cost", "fieldtype": "Check", "read_only": 1, "insert_after": "hml_needs_discount_approval"},
		{"fieldname": "hml_discount_reason", "label": "Discount Reason", "fieldtype": "Small Text", "insert_after": "hml_below_cost",
			"description": "Mandatory when any manual discount is given."},
		{"fieldname": "hml_discount_approved_by", "label": "Discount Approved By", "fieldtype": "Link", "options": "User", "read_only": 1, "insert_after": "hml_discount_reason", "allow_on_submit": 1},
		{"fieldname": "hml_discount_approved_on", "label": "Discount Approved On", "fieldtype": "Datetime", "read_only": 1, "insert_after": "hml_discount_approved_by", "allow_on_submit": 1},
		{"fieldname": "hml_delivery_section", "label": "Delivery Estimate", "fieldtype": "Section Break", "insert_after": "hml_discount_approved_on"},
		{"fieldname": "hml_estimated_delivery_date", "label": "Earliest Achievable Delivery", "fieldtype": "Date", "read_only": 1, "insert_after": "hml_delivery_section",
			"description": "Latest of the item estimates: stock on hand ships in 2 days; otherwise component lead time + manufacturing lead time + 2 days."},
		{"fieldname": "hml_delivery_risk", "label": "Promised Before Achievable Date", "fieldtype": "Check", "read_only": 1, "insert_after": "hml_estimated_delivery_date"},
		{"fieldname": "hml_credit_exposure", "label": "Credit Exposure incl. this order", "fieldtype": "Currency", "read_only": 1, "insert_after": "hml_delivery_risk"},
		{"fieldname": "hml_credit_override_reason", "label": "Credit Limit Override Reason", "fieldtype": "Small Text", "insert_after": "hml_credit_exposure",
			"description": "Only the Finance Director / Accounts Manager can submit an order beyond the customer's credit limit, with a reason."},
	]


def _planning_item_fields(after):
	"""Per-row stock / BOM / lead-time info on Quotation Item and Sales Order Item."""
	return [
		{"fieldname": "hml_planning_section", "label": "Availability and Lead Time", "fieldtype": "Section Break", "insert_after": after},
		{"fieldname": "hml_available_qty", "label": "Available Qty (all HML locations)", "fieldtype": "Float", "read_only": 1, "insert_after": "hml_planning_section", "in_list_view": 0},
		{"fieldname": "hml_bom", "label": "Master BOM", "fieldtype": "Link", "options": "BOM", "read_only": 1, "insert_after": "hml_available_qty"},
		{"fieldname": "hml_unit_cost", "label": "Standard Unit Cost", "fieldtype": "Currency", "read_only": 1, "insert_after": "hml_bom",
			"description": "BOM cost for manufactured items, valuation rate for bought items."},
		{"fieldname": "hml_col_planning", "fieldtype": "Column Break", "insert_after": "hml_unit_cost"},
		{"fieldname": "hml_lead_time_days", "label": "Lead Time (days)", "fieldtype": "Int", "read_only": 1, "insert_after": "hml_col_planning"},
		{"fieldname": "hml_estimated_delivery_date", "label": "Estimated Delivery", "fieldtype": "Date", "read_only": 1, "insert_after": "hml_lead_time_days", "in_list_view": 1, "columns": 1},
		{"fieldname": "hml_estimate_basis", "label": "Estimate Basis", "fieldtype": "Small Text", "read_only": 1, "insert_after": "hml_estimated_delivery_date"},
	]


DELIVERY_NOTE_FIELDS = [
	{"fieldname": "hml_pod_section", "label": "Proof of Delivery", "fieldtype": "Section Break", "insert_after": "instructions"},
	{"fieldname": "hml_pod_status", "label": "POD Status", "fieldtype": "Select", "options": "Pending\nReceived\nReceived with Remarks", "default": "Pending", "insert_after": "hml_pod_section", "allow_on_submit": 1, "in_standard_filter": 1},
	{"fieldname": "hml_received_by", "label": "Received By (name)", "fieldtype": "Data", "insert_after": "hml_pod_status", "allow_on_submit": 1},
	{"fieldname": "hml_received_on", "label": "Received On", "fieldtype": "Datetime", "insert_after": "hml_received_by", "allow_on_submit": 1},
	{"fieldname": "hml_col_pod", "fieldtype": "Column Break", "insert_after": "hml_received_on"},
	{"fieldname": "hml_customer_signature", "label": "Customer Signature", "fieldtype": "Signature", "insert_after": "hml_col_pod", "allow_on_submit": 1},
	{"fieldname": "hml_deviation_section", "label": "Quantity Deviation", "fieldtype": "Section Break", "insert_after": "hml_customer_signature"},
	{"fieldname": "hml_has_deviation", "label": "Delivered Qty Differs from Sales Order", "fieldtype": "Check", "read_only": 1, "insert_after": "hml_deviation_section"},
	{"fieldname": "hml_deviation_notes", "label": "Deviation Notes", "fieldtype": "Small Text", "insert_after": "hml_has_deviation",
		"mandatory_depends_on": "eval:doc.hml_has_deviation", "description": "Why the delivered quantity differs from the open Sales Order quantity (partial shipment, short pick, customer request)."},
]

LEAD_FIELDS = [
	{"fieldname": "hml_estimated_value", "label": "Estimated Deal Value", "fieldtype": "Currency", "insert_after": "source"},
	{"fieldname": "hml_product_interest", "label": "Product Interest", "fieldtype": "Select", "options": "\nEquipment\nSpares\nComponents\nCustom Project", "insert_after": "hml_estimated_value"},
]


PURCHASE_ORDER_FIELDS = [
	{"fieldname": "hml_approval_section", "label": "Approval", "fieldtype": "Section Break", "insert_after": "in_words"},
	{"fieldname": "hml_approval_tier", "label": "Approval Tier", "fieldtype": "Select", "options": "\n1 - Dept Head\n2 - Dept Head + Procurement\n3 - Dept Head + Procurement + Finance Director",
		"read_only": 1, "insert_after": "hml_approval_section", "in_standard_filter": 1,
		"description": "Below Rs 1 L: tier 1. Rs 1-5 L: tier 2. Above Rs 5 L or blacklisted supplier: tier 3."},
	{"fieldname": "hml_urgency", "label": "Urgency", "fieldtype": "Select", "options": "Normal\nUrgent\nCritical - Line Stoppage", "default": "Normal", "insert_after": "hml_approval_tier", "in_standard_filter": 1},
	{"fieldname": "hml_state_since", "label": "In Current Approval State Since", "fieldtype": "Datetime", "read_only": 1, "insert_after": "hml_urgency", "allow_on_submit": 1, "no_copy": 1},
	{"fieldname": "hml_escalation_count", "label": "Auto-escalations", "fieldtype": "Int", "read_only": 1, "insert_after": "hml_state_since", "no_copy": 1, "allow_on_submit": 1},
	{"fieldname": "hml_col_approval", "fieldtype": "Column Break", "insert_after": "hml_escalation_count"},
	{"fieldname": "hml_supplier_blacklisted", "label": "Supplier Blacklisted", "fieldtype": "Check", "read_only": 1, "insert_after": "hml_col_approval", "no_copy": 1},
	{"fieldname": "hml_blacklist_override_reason", "label": "Blacklist Override Reason", "fieldtype": "Small Text", "insert_after": "hml_supplier_blacklisted",
		"depends_on": "hml_supplier_blacklisted", "mandatory_depends_on": "hml_supplier_blacklisted",
		"description": "Why this blacklisted supplier must be used (e.g. sole source). Logged for audit and escalated to the Finance Director."},
	{"fieldname": "hml_rejection_comment", "label": "Last Rejection Comment", "fieldtype": "Small Text", "read_only": 1, "insert_after": "hml_blacklist_override_reason", "no_copy": 1},
]

QUALITY_INSPECTION_FIELDS = [
	{"fieldname": "hml_result_section", "label": "Horizon Result", "fieldtype": "Section Break", "insert_after": "remarks"},
	{"fieldname": "hml_result", "label": "Result", "fieldtype": "Select", "options": "\nPass\nConditional Pass\nFail\nRework", "insert_after": "hml_result_section", "in_list_view": 1, "in_standard_filter": 1,
		"description": "Pass / Conditional Pass set status Accepted; Fail / Rework set Rejected."},
	{"fieldname": "hml_rejection_reason", "label": "Rejection Reason", "fieldtype": "Link", "options": "Quality Rejection Reason", "insert_after": "hml_result",
		"depends_on": "eval:['Fail','Rework'].includes(doc.hml_result)", "mandatory_depends_on": "eval:['Fail','Rework'].includes(doc.hml_result)"},
	{"fieldname": "hml_rejected_qty", "label": "Rejected Qty", "fieldtype": "Float", "insert_after": "hml_rejection_reason",
		"depends_on": "eval:['Fail','Rework'].includes(doc.hml_result)"},
	{"fieldname": "hml_concession_note", "label": "Concession / Deviation Note", "fieldtype": "Small Text", "insert_after": "hml_rejected_qty",
		"depends_on": "eval:doc.hml_result=='Conditional Pass'", "mandatory_depends_on": "eval:doc.hml_result=='Conditional Pass'",
		"description": "Accepted with deviation: what is out of spec and who agreed to use it."},
	{"fieldname": "hml_col_result", "fieldtype": "Column Break", "insert_after": "hml_concession_note"},
	{"fieldname": "hml_evidence_photo", "label": "Evidence Photo", "fieldtype": "Attach Image", "insert_after": "hml_col_result",
		"mandatory_depends_on": "eval:['Fail','Rework'].includes(doc.hml_result)", "description": "Mandatory for failed items."},
	{"fieldname": "hml_received_at", "label": "Goods Received At", "fieldtype": "Datetime", "read_only": 1, "insert_after": "hml_evidence_photo"},
	{"fieldname": "hml_inspection_hours", "label": "Hours from Receipt to Inspection", "fieldtype": "Float", "read_only": 1, "insert_after": "hml_received_at", "precision": "1"},
	{"fieldname": "hml_sla_met", "label": "Inspection SLA Met (4 h)", "fieldtype": "Check", "read_only": 1, "insert_after": "hml_inspection_hours"},
	{"fieldname": "hml_supplier", "label": "Supplier", "fieldtype": "Link", "options": "Supplier", "read_only": 1, "insert_after": "hml_sla_met", "in_standard_filter": 1},
	{"fieldname": "hml_item_group", "label": "Item Category", "fieldtype": "Link", "options": "Item Group", "read_only": 1, "insert_after": "hml_supplier", "fetch_from": "item_code.item_group"},
]

MATERIAL_REQUEST_FIELDS = [
	{"fieldname": "hml_supplier", "label": "Grouped for Supplier", "fieldtype": "Link", "options": "Supplier", "insert_after": "material_request_type", "read_only": 1,
		"description": "Set by the hourly reorder job, which raises one request per default supplier."},
	{"fieldname": "hml_auto_reorder", "label": "Auto Reorder", "fieldtype": "Check", "read_only": 1, "insert_after": "hml_supplier"},
]


WORKSTATION_FIELDS = [
	{"fieldname": "hml_capacity_section", "label": "Horizon Capacity", "fieldtype": "Section Break", "insert_after": "holiday_list"},
	{"fieldname": "hml_setup_time_mins", "label": "Setup / Changeover Time (min)", "fieldtype": "Int", "insert_after": "hml_capacity_section",
		"description": "Added once per Work Order (product changeover)."},
	{"fieldname": "hml_downtime_pct", "label": "Planned Downtime %", "fieldtype": "Percent", "insert_after": "hml_setup_time_mins",
		"description": "Maintenance, breakdowns and breaks; reduces usable hours."},
	{"fieldname": "hml_effective_hours_per_day", "label": "Usable Hours per Day", "fieldtype": "Float", "read_only": 1, "insert_after": "hml_downtime_pct"},
]

QI_TEMPLATE_FIELDS = [
	{"fieldname": "hml_photo_required", "label": "Critical Check - Photo / Video Evidence Required", "fieldtype": "Check", "insert_after": "quality_inspection_template_name"},
]

BOM_FIELDS = [
	{"fieldname": "hml_revision_section", "label": "Revision Control", "fieldtype": "Section Break", "insert_after": "description"},
	{"fieldname": "hml_revision_no", "label": "Revision No", "fieldtype": "Int", "read_only": 1, "insert_after": "hml_revision_section"},
	{"fieldname": "hml_revision_reason", "label": "Revision Trigger", "fieldtype": "Select", "insert_after": "hml_revision_no",
		"options": "\nInitial Release\nDesign Change\nCost Update\nSupplier / Material Change\nQuality Improvement\nProcess Change",
		"description": "Mandatory. Why this BOM version exists (audit requirement)."},
	{"fieldname": "hml_col_revision", "fieldtype": "Column Break", "insert_after": "hml_revision_reason"},
	{"fieldname": "hml_ecn_no", "label": "Engineering Change Note No", "fieldtype": "Data", "insert_after": "hml_col_revision"},
	{"fieldname": "hml_revision_notes", "label": "What Changed", "fieldtype": "Small Text", "insert_after": "hml_ecn_no"},
	{"fieldname": "hml_supersedes", "label": "Supersedes BOM", "fieldtype": "Link", "options": "BOM", "read_only": 1, "insert_after": "hml_revision_notes"},
]

BOM_OPERATION_FIELDS = [
	{"fieldname": "hml_inspection_template", "label": "Inspection Checkpoint", "fieldtype": "Link", "options": "Quality Inspection Template",
		"fetch_from": "operation.quality_inspection_template", "read_only": 1, "insert_after": "workstation", "in_list_view": 1, "columns": 2},
]

WORK_ORDER_FIELDS = [
	{"fieldname": "hml_capacity_tab", "label": "Capacity and Quality", "fieldtype": "Tab Break", "insert_after": "description"},
	{"fieldname": "hml_production_line", "label": "Production Line", "fieldtype": "Link", "options": "Workstation", "insert_after": "hml_capacity_tab",
		"description": "Auto-assigned to the eligible line with most free hours before the deadline; can be overridden."},
	{"fieldname": "hml_deadline", "label": "Must Finish By", "fieldtype": "Date", "insert_after": "hml_production_line",
		"description": "Sales Order delivery date minus 2 dispatch days, else planned end date."},
	{"fieldname": "hml_required_hours", "label": "Required Line Hours", "fieldtype": "Float", "read_only": 1, "insert_after": "hml_deadline"},
	{"fieldname": "hml_line_free_hours", "label": "Free Line Hours Before Deadline", "fieldtype": "Float", "read_only": 1, "insert_after": "hml_required_hours"},
	{"fieldname": "hml_capacity_status", "label": "Capacity Check", "fieldtype": "Select", "options": "\nOK\nOver Capacity - Decision Recorded", "read_only": 1,
		"insert_after": "hml_line_free_hours", "in_standard_filter": 1},
	{"fieldname": "hml_col_capacity", "fieldtype": "Column Break", "insert_after": "hml_capacity_status"},
	{"fieldname": "hml_capacity_decision", "label": "Capacity Decision", "fieldtype": "Select", "insert_after": "hml_col_capacity",
		"options": "\nShip Partial\nDelay Delivery (customer agreed)\nOvertime / Extra Shift\nMove to Other Line\nNegotiate Timeline",
		"description": "Required when the line cannot finish before the deadline. Forces a business decision instead of hiding the conflict."},
	{"fieldname": "hml_capacity_decision_note", "label": "Decision Note", "fieldtype": "Small Text", "insert_after": "hml_capacity_decision"},
	{"fieldname": "hml_decided_by", "label": "Decided By", "fieldtype": "Link", "options": "User", "read_only": 1, "insert_after": "hml_capacity_decision_note"},
	{"fieldname": "hml_quality_section", "label": "Quality", "fieldtype": "Section Break", "insert_after": "hml_decided_by"},
	{"fieldname": "hml_has_rework", "label": "Had Rework", "fieldtype": "Check", "read_only": 1, "insert_after": "hml_quality_section", "allow_on_submit": 1, "no_copy": 1},
	{"fieldname": "hml_rework_qty", "label": "Units Reworked", "fieldtype": "Float", "read_only": 1, "insert_after": "hml_has_rework", "allow_on_submit": 1, "no_copy": 1},
	{"fieldname": "hml_audit_hold", "label": "On Hold - Production Audit Below 70", "fieldtype": "Check", "read_only": 1, "insert_after": "hml_rework_qty", "allow_on_submit": 1, "no_copy": 1},
]

JOB_CARD_FIELDS = [
	{"fieldname": "hml_production_line", "label": "Production Line", "fieldtype": "Link", "options": "Workstation",
		"fetch_from": "work_order.hml_production_line", "read_only": 1, "insert_after": "workstation"},
]

NON_CONFORMANCE_FIELDS = [
	{"fieldname": "hml_section", "label": "Defect Details", "fieldtype": "Section Break", "insert_after": "status"},
	{"fieldname": "hml_company", "label": "Company", "fieldtype": "Link", "options": "Company", "insert_after": "hml_section", "default": "Horizon Manufacturing Ltd"},
	{"fieldname": "hml_source", "label": "Detected At", "fieldtype": "Select", "options": "\nIncoming Inspection\nIn-Process Inspection\nFinal Testing\nProduction Audit\nCustomer Complaint",
		"insert_after": "hml_company", "in_list_view": 1, "in_standard_filter": 1},
	{"fieldname": "hml_item_code", "label": "Item", "fieldtype": "Link", "options": "Item", "insert_after": "hml_source", "in_standard_filter": 1},
	{"fieldname": "hml_defect_reason", "label": "Defect Reason", "fieldtype": "Link", "options": "Quality Rejection Reason", "insert_after": "hml_item_code", "in_standard_filter": 1},
	{"fieldname": "hml_defect_qty", "label": "Defective Qty", "fieldtype": "Float", "insert_after": "hml_defect_reason"},
	{"fieldname": "hml_cost_impact", "label": "Cost Impact (rework / scrap)", "fieldtype": "Currency", "insert_after": "hml_defect_qty"},
	{"fieldname": "hml_col_links", "fieldtype": "Column Break", "insert_after": "hml_cost_impact"},
	{"fieldname": "hml_work_order", "label": "Work Order", "fieldtype": "Link", "options": "Work Order", "insert_after": "hml_col_links"},
	{"fieldname": "hml_job_card", "label": "Job Card", "fieldtype": "Link", "options": "Job Card", "insert_after": "hml_work_order"},
	{"fieldname": "hml_quality_inspection", "label": "Quality Inspection", "fieldtype": "Link", "options": "Quality Inspection", "insert_after": "hml_job_card"},
	{"fieldname": "hml_supplier", "label": "Supplier (if material defect)", "fieldtype": "Link", "options": "Supplier", "insert_after": "hml_quality_inspection",
		"description": "Links the defect to supplier quality; feeds the Supplier Quality Scorecard review."},
	{"fieldname": "hml_rca_section", "label": "Root Cause Analysis", "fieldtype": "Section Break", "insert_after": "hml_supplier"},
	{"fieldname": "hml_rca_method", "label": "Method", "fieldtype": "Select", "options": "\n5-Why\nFishbone (6M)\nFault Tree", "insert_after": "hml_rca_section"},
	{"fieldname": "hml_root_cause_category", "label": "Root Cause Category (6M)", "fieldtype": "Select", "options": "\nMan\nMachine\nMethod\nMaterial\nMeasurement\nMother Nature", "insert_after": "hml_rca_method", "in_standard_filter": 1},
	{"fieldname": "hml_root_cause", "label": "Root Cause", "fieldtype": "Small Text", "insert_after": "hml_root_cause_category"},
	{"fieldname": "hml_corrective_action", "label": "Corrective Action Plan", "fieldtype": "Link", "options": "Corrective Action", "insert_after": "hml_root_cause"},
]


TASK_FIELDS = [
	{"fieldname": "hml_billing_section", "label": "Milestone Billing", "fieldtype": "Section Break", "insert_after": "is_milestone", "depends_on": "is_milestone"},
	{"fieldname": "hml_billing_pct", "label": "Billing % of Contract", "fieldtype": "Percent", "insert_after": "hml_billing_section",
		"description": "When this milestone task is Completed, a Sales Invoice for this share of the Sales Order is raised automatically."},
	{"fieldname": "hml_billing_amount", "label": "Billing Amount", "fieldtype": "Currency", "read_only": 1, "insert_after": "hml_billing_pct"},
	{"fieldname": "hml_milestone_invoice", "label": "Milestone Invoice", "fieldtype": "Link", "options": "Sales Invoice", "read_only": 1, "insert_after": "hml_billing_amount", "no_copy": 1},
	{"fieldname": "hml_budgeted_cost", "label": "Budgeted Cost", "fieldtype": "Currency", "insert_after": "hml_milestone_invoice"},
]

PROJECT_FIELDS = [
	{"fieldname": "hml_costing_section", "label": "Horizon Project Costing", "fieldtype": "Section Break", "insert_after": "per_gross_margin"},
	{"fieldname": "hml_contract_value", "label": "Contract Value (Sales Order)", "fieldtype": "Currency", "read_only": 1, "insert_after": "hml_costing_section"},
	{"fieldname": "hml_overhead_pct", "label": "Overhead % of Direct Cost", "fieldtype": "Percent", "default": "15", "insert_after": "hml_contract_value"},
	{"fieldname": "hml_labour_cost", "label": "Labour (timesheets)", "fieldtype": "Currency", "read_only": 1, "insert_after": "hml_overhead_pct"},
	{"fieldname": "hml_material_cost", "label": "Material (issues + purchases)", "fieldtype": "Currency", "read_only": 1, "insert_after": "hml_labour_cost"},
	{"fieldname": "hml_col_cost", "fieldtype": "Column Break", "insert_after": "hml_material_cost"},
	{"fieldname": "hml_overhead_cost", "label": "Overhead (allocated)", "fieldtype": "Currency", "read_only": 1, "insert_after": "hml_col_cost"},
	{"fieldname": "hml_total_cost", "label": "Total Cost", "fieldtype": "Currency", "read_only": 1, "insert_after": "hml_overhead_cost"},
	{"fieldname": "hml_billed_amount", "label": "Billed (milestones)", "fieldtype": "Currency", "read_only": 1, "insert_after": "hml_total_cost"},
	{"fieldname": "hml_margin_pct", "label": "Margin % (on cost to date vs earned)", "fieldtype": "Percent", "read_only": 1, "insert_after": "hml_billed_amount"},
	{"fieldname": "hml_budget_margin_pct", "label": "Budgeted Margin %", "fieldtype": "Percent", "read_only": 1, "insert_after": "hml_margin_pct"},
]

TIMESHEET_FIELDS = [
	{"fieldname": "hml_has_overtime", "label": "Overtime (> 8 h on a day)", "fieldtype": "Check", "read_only": 1, "insert_after": "total_hours", "in_standard_filter": 1},
	{"fieldname": "hml_overtime_hours", "label": "Overtime Hours", "fieldtype": "Float", "read_only": 1, "insert_after": "hml_has_overtime",
		"description": "Hours above 8 per employee per day, across all of that employee's timesheets. Paid via payroll (Overtime component)."},
]

EMPLOYEE_FIELDS = [
	{"fieldname": "hml_employee_category", "label": "Pay Category", "fieldtype": "Select", "options": "\nSalaried Staff\nWage Earner\nContractual",
		"insert_after": "branch", "in_standard_filter": 1, "description": "Drives the salary structure: monthly CTC, hourly wages, or fixed contract fee."},
	{"fieldname": "hml_hourly_rate", "label": "Hourly Wage Rate", "fieldtype": "Currency", "insert_after": "hml_employee_category", "depends_on": "eval:doc.hml_employee_category=='Wage Earner'"},
]

SALARY_SLIP_FIELDS = [
	{"fieldname": "hml_hours_section", "label": "Hours (wage earners)", "fieldtype": "Section Break", "insert_after": "payment_days"},
	{"fieldname": "hml_employee_category", "label": "Pay Category", "fieldtype": "Data", "read_only": 1, "insert_after": "hml_hours_section"},
	{"fieldname": "hml_hours_worked", "label": "Hours Worked (attendance)", "fieldtype": "Float", "read_only": 1, "insert_after": "hml_employee_category"},
	{"fieldname": "hml_overtime_hours", "label": "Overtime Hours", "fieldtype": "Float", "read_only": 1, "insert_after": "hml_hours_worked",
		"description": "Attendance hours above 8 per day + timesheet overtime not already covered by attendance."},
]

SALES_INVOICE_FIELDS = [
	{"fieldname": "hml_milestone_section", "label": "Project Milestone", "fieldtype": "Section Break", "insert_after": "project", "depends_on": "hml_project_milestone"},
	{"fieldname": "hml_project_milestone", "label": "Milestone Task", "fieldtype": "Link", "options": "Task", "read_only": 1, "insert_after": "hml_milestone_section"},
	{"fieldname": "hml_material_cost", "label": "Material Cost to Date", "fieldtype": "Currency", "read_only": 1, "insert_after": "hml_project_milestone"},
	{"fieldname": "hml_labour_cost", "label": "Labour Cost to Date", "fieldtype": "Currency", "read_only": 1, "insert_after": "hml_material_cost"},
	{"fieldname": "hml_overhead_cost", "label": "Overhead to Date", "fieldtype": "Currency", "read_only": 1, "insert_after": "hml_labour_cost"},
]

ASSET_FIELDS = [
	{"fieldname": "hml_asset_section", "label": "Horizon", "fieldtype": "Section Break", "insert_after": "cost_center"},
	{"fieldname": "hml_production_line", "label": "Production Line", "fieldtype": "Link", "options": "Workstation", "insert_after": "hml_asset_section"},
	{"fieldname": "hml_replacement_flag", "label": "Replacement Candidate", "fieldtype": "Check", "read_only": 1, "insert_after": "hml_production_line", "allow_on_submit": 1,
		"description": "Set by the Asset Register when maintenance cost in the last 12 months exceeds 15 % of book value."},
	{"fieldname": "hml_retirement_reason", "label": "Retirement Reason", "fieldtype": "Small Text", "insert_after": "hml_replacement_flag", "allow_on_submit": 1},
]


BANK_ACCOUNT_FIELDS = [
	{"fieldname": "hml_reconciliation_frequency", "label": "Reconciliation Frequency", "fieldtype": "Select", "options": "\nDaily\nWeekly\nMonthly",
		"default": "Monthly", "insert_after": "account"},
	{"fieldname": "hml_reconciled_upto", "label": "Reconciled and Locked Up To", "fieldtype": "Date", "read_only": 1, "insert_after": "hml_reconciliation_frequency"},
	{"fieldname": "hml_statement_opening", "label": "Statement Opening Balance", "fieldtype": "Currency", "insert_after": "hml_reconciled_upto",
		"description": "Bank balance before the first imported statement line (agreed to the GL at go-live)."},
]

BANK_TRANSACTION_FIELDS = [
	{"fieldname": "hml_exception_section", "label": "Reconciliation Exception", "fieldtype": "Section Break", "insert_after": "unallocated_amount"},
	{"fieldname": "hml_exception_type", "label": "Exception Type", "fieldtype": "Select", "allow_on_submit": 1, "insert_after": "hml_exception_section",
		"options": "\nPost-dated Cheque\nCheque in Clearing\nTiming Difference\nBank Charge to Book\nInterest to Book\nUnidentified Receipt\nDisputed",
		"in_standard_filter": 1},
	{"fieldname": "hml_exception_note", "label": "Exception Note", "fieldtype": "Small Text", "allow_on_submit": 1, "insert_after": "hml_exception_type"},
	{"fieldname": "hml_auto_matched", "label": "Auto-matched By", "fieldtype": "Data", "read_only": 1, "allow_on_submit": 1, "insert_after": "hml_exception_note"},
]

COST_CENTER_FIELDS = [
	{"fieldname": "hml_owner", "label": "Budget Owner", "fieldtype": "Link", "options": "User", "insert_after": "company",
		"description": "Receives the monthly budget performance mail and the 90 % alert."},
]

COMPANY_FIELDS = [
	{"fieldname": "hml_invoice_terms", "label": "Invoice Terms and Conditions", "fieldtype": "Text Editor", "insert_after": "default_operating_cost_account",
		"description": "Printed on Horizon tax invoices."},
]


def get_custom_fields():
	return {
		"Item": ITEM_FIELDS,
		"Supplier": SUPPLIER_FIELDS,
		"Stock Reconciliation": STOCK_RECO_FIELDS,
		"Quotation": _pricing_fields("in_words"),
		"Sales Order": _pricing_fields("in_words"),
		"Quotation Item": _planning_item_fields("projected_qty"),
		"Sales Order Item": _planning_item_fields("transaction_date"),
		"Delivery Note": DELIVERY_NOTE_FIELDS,
		"Lead": LEAD_FIELDS,
		"Purchase Order": PURCHASE_ORDER_FIELDS,
		"Quality Inspection": QUALITY_INSPECTION_FIELDS,
		"Material Request": MATERIAL_REQUEST_FIELDS,
		"Workstation": WORKSTATION_FIELDS,
		"Quality Inspection Template": QI_TEMPLATE_FIELDS,
		"BOM": BOM_FIELDS,
		"BOM Operation": BOM_OPERATION_FIELDS,
		"Work Order": WORK_ORDER_FIELDS,
		"Job Card": JOB_CARD_FIELDS,
		"Non Conformance": NON_CONFORMANCE_FIELDS,
		"Task": TASK_FIELDS,
		"Project": PROJECT_FIELDS,
		"Timesheet": TIMESHEET_FIELDS,
		"Employee": EMPLOYEE_FIELDS,
		"Salary Slip": SALARY_SLIP_FIELDS,
		"Sales Invoice": SALES_INVOICE_FIELDS,
		"Asset": ASSET_FIELDS,
		"Bank Account": BANK_ACCOUNT_FIELDS,
		"Bank Transaction": BANK_TRANSACTION_FIELDS,
		"Cost Center": COST_CENTER_FIELDS,
		"Company": COMPANY_FIELDS,
	}
