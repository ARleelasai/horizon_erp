frappe.query_reports["HML Asset Register"] = {
	filters: [
		{ fieldname: "as_on_date", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "include_disposed", label: __("Include sold / scrapped"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.replace && ["asset_name", "maintenance_12m_pct"].includes(column.fieldname)) return `<span style="color: var(--red-600); font-weight:600">${value}</span>`;
		return value;
	},
};
