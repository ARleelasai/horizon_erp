frappe.query_reports["HML BOM Explosion"] = {
	filters: [
		{ fieldname: "item_code", label: __("Finished Item"), fieldtype: "Link", options: "Item", default: "HX-500" },
		{ fieldname: "bom", label: __("BOM (default if blank)"), fieldtype: "Link", options: "BOM" },
		{ fieldname: "qty", label: __("Units to Build"), fieldtype: "Float", default: 1 },
		{ fieldname: "hide_operations", label: __("Hide operations"), fieldtype: "Check" },
	],
	tree: true,
	name_field: "item_code",
	parent_field: "",
	initial_depth: 3,
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "shortfall" && data.shortfall > 0) return `<span style="color: var(--red-600); font-weight:600">${value}</span>`;
		if (data && data.source === "Operation") return `<span style="color: var(--text-muted)">${value}</span>`;
		return value;
	},
};
