frappe.query_reports["HML API Usage"] = {
	filters: [
		{ fieldname: "view", label: __("View"), fieldtype: "Select", options: ["By Client", "Response Time Trend", "Failures"], default: "By Client" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -7) },
	],
};
