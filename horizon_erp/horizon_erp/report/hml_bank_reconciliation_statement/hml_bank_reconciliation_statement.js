frappe.query_reports["HML Bank Reconciliation Statement"] = {
	filters: [
		{ fieldname: "bank_account", label: __("Bank Account"), fieldtype: "Link", options: "Bank Account" },
		{ fieldname: "as_on_date", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.flag && ["age", "reference"].includes(column.fieldname)) return `<span style="color: var(--red-600); font-weight:600">${value}</span>`;
		return value;
	},
};
