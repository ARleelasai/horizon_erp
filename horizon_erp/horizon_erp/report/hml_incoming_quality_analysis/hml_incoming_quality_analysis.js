frappe.query_reports["HML Incoming Quality Analysis"] = {
	filters: [
		{ fieldname: "view", label: __("View"), fieldtype: "Select", options: ["By Supplier", "By Item Category", "Inspection SLA"], default: "By Supplier", reqd: 1 },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: "2026-04-01" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "hours" && data.hours > 4) return `<span style="color: var(--red-600); font-weight:600">${value}</span>`;
		return value;
	},
};
