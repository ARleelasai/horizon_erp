frappe.query_reports["HML Budget Variance"] = {
	filters: [
		{ fieldname: "fiscal_year", label: __("Fiscal Year"), fieldtype: "Link", options: "Fiscal Year", default: "2026-2027" },
		{ fieldname: "upto", label: __("Up To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "cost_center", label: __("Cost Center"), fieldtype: "Link", options: "Cost Center" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "ytd_var_pct" && data.over_10) return `<span style="color: var(--red-600); font-weight:600">${value}</span>`;
		if (column.fieldname === "ytd_var_pct" && data.ytd_var_pct < 0) return `<span style="color: var(--green-600)">${value}</span>`;
		if (column.fieldname === "used_pct" && data.alert_90) return `<span class="indicator-pill orange">${value}</span>`;
		return value;
	},
};
