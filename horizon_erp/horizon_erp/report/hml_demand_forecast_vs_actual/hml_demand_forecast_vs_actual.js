frappe.query_reports["HML Demand Forecast vs Actual"] = {
	filters: [
		{ fieldname: "from_month", label: __("From Month"), fieldtype: "Date", default: "2025-10-01" },
		{ fieldname: "to_month", label: __("To Month"), fieldtype: "Date", default: "2026-10-01" },
		{ fieldname: "item_group", label: __("Category"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item", default: "SP-SEAL-KIT-HX" },
		{ fieldname: "summary_only", label: __("One row per item (accuracy)"), fieldtype: "Check" },
	],
};
