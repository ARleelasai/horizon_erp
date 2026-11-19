frappe.query_reports["HML Approval Audit Report"] = {
	filters: [
		{ fieldname: "from_date", label: __("PO Date From"), fieldtype: "Date", default: "2026-04-01" },
		{ fieldname: "purchase_order", label: __("Purchase Order"), fieldtype: "Link", options: "Purchase Order" },
	],
};
