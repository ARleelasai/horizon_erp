frappe.query_reports["HML Supplier Quality Scorecard"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: "2026-04-01" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "grade") {
			const color = { A: "green", B: "orange", C: "red" }[data.grade];
			return `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return value;
	},
};
