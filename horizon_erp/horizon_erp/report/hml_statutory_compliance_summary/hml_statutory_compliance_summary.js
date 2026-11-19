frappe.query_reports["HML Statutory Compliance Summary"] = {
	filters: [
		{ fieldname: "from_date", label: __("Payroll From"), fieldtype: "Date", default: "2026-10-01" },
		{ fieldname: "to_date", label: __("Payroll To"), fieldtype: "Date", default: "2026-10-31" },
	],
};
