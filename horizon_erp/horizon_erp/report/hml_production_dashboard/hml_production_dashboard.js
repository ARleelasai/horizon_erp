frappe.query_reports["HML Production Dashboard"] = {
	filters: [
		{ fieldname: "from_date", label: __("Utilisation From"), fieldtype: "Date", default: "2026-11-01" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "only_open", label: __("Only open Work Orders"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "schedule_variance_days" && data.schedule_variance_days > 0) return `<span style="color: var(--red-600)">${value}</span>`;
		if (data && column.fieldname === "quality_issues" && data.quality_issues) return `<span class="indicator-pill red">${value}</span>`;
		return value;
	},
};
