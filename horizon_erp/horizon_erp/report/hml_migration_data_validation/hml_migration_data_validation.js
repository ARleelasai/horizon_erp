frappe.query_reports["HML Migration Data Validation"] = {
	filters: [
		{ fieldname: "view", label: __("View"), fieldtype: "Select", options: ["Summary", "Detail"], default: "Summary" },
		{ fieldname: "entity", label: __("Entity"), fieldtype: "Select", options: ["", "Customer", "Item Stock", "Purchase Invoice"] },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Pending", "Auto-fixed", "Needs Review", "Approved for Import", "Imported", "Rejected"] },
	],
};
