frappe.query_reports["HML Quality Metrics"] = {
	filters: [
		{ fieldname: "view", label: __("View"), fieldtype: "Select", options: ["First-Pass Yield", "Defect Trend"], default: "First-Pass Yield", reqd: 1 },
	],
};
