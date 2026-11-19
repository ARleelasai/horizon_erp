frappe.query_reports["HML Location PnL vs Budget"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: "2026-04-01" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.line === "Net margin %" && column.fieldtype === "Currency") return `${(data[column.fieldname] || 0).toFixed(1)} %`;
		if (data && data.bold) return `<b>${value}</b>`;
		return value;
	},
};
