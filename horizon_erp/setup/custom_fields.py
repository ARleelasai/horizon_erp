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


def get_custom_fields():
	return {
		"Item": ITEM_FIELDS,
		"Supplier": SUPPLIER_FIELDS,
		"Stock Reconciliation": STOCK_RECO_FIELDS,
	}
