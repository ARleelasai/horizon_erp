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
	}
