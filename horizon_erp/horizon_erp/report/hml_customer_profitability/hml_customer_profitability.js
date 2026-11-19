frappe.query_reports["HML Customer Profitability"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: "2026-04-01" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "top", label: __("Top N"), fieldtype: "Int", default: 10 },
	],
};
