frappe.query_reports["HML Production Schedule"] = {
	filters: [
		{ fieldname: "start_date", label: __("Schedule From"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "line", label: __("Line"), fieldtype: "Link", options: "Workstation" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.late && ["work_order", "projected_finish", "days_late", "item_code"].includes(column.fieldname)) {
			return `<span style="color: var(--red-600); font-weight:600">${value}</span>`;
		}
		return value;
	},
};
