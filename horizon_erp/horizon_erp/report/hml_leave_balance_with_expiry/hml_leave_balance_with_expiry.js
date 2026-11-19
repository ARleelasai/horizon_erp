frappe.query_reports["HML Leave Balance with Expiry"] = {
	filters: [{ fieldname: "date", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() }],
};
