frappe.query_reports["HML GST Summary by Registration"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: "2026-04-01" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
};
