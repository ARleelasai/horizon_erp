frappe.query_reports["HML Budget Performance Analysis"] = {
	filters: [
		{ fieldname: "fiscal_year", label: __("Fiscal Year"), fieldtype: "Link", options: "Fiscal Year", default: "2026-2027" },
		{ fieldname: "upto", label: __("Up To"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
};
