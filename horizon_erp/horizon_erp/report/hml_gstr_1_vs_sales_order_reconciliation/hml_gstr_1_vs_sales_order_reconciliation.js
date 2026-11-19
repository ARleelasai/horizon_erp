frappe.query_reports["HML GSTR-1 vs Sales Order Reconciliation"] = {
	filters: [
		{ fieldname: "from_date", label: __("Return Period From"), fieldtype: "Date", default: "2026-04-01" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "status") {
			const ok = data.status.startsWith("Matched") || data.status.startsWith("Asset");
			return `<span class="indicator-pill ${ok ? "green" : "red"}">${value}</span>`;
		}
		return value;
	},
};
