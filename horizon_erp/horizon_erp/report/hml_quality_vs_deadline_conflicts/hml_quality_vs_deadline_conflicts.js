frappe.query_reports["HML Quality vs Deadline Conflicts"] = {
	filters: [{ fieldname: "horizon_days", label: __("Due Within (days)"), fieldtype: "Int", default: 7 }],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.section === "At risk" && ["sales_order", "days_left"].includes(column.fieldname)) return `<span style="color: var(--red-600); font-weight:600">${value}</span>`;
		return value;
	},
};
