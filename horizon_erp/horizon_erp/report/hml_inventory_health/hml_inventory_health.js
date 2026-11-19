frappe.query_reports["HML Inventory Health"] = {
	filters: [
		{ fieldname: "as_on_date", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "only_exceptions", label: __("Only red / yellow"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "status") {
			const color = { "Below Reorder": "red", "Aging > 90 d": "yellow", Healthy: "green" }[data.status];
			return `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return value;
	},
};
