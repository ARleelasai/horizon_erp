frappe.query_reports["HML Audit Trail"] = {
	filters: [
		{ fieldname: "ref_doctype", label: __("Document Type"), fieldtype: "Link", options: "DocType" },
		{ fieldname: "user", label: __("User"), fieldtype: "Link", options: "User" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "limit", label: __("Max Rows"), fieldtype: "Int", default: 1000 },
	],
};
