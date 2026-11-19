frappe.query_reports["HML Salary Cost Analysis"] = {
	filters: [
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select", options: ["Department", "Grade", "Pay Category", "Branch"], default: "Department" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: "2026-04-01" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: "2027-03-31" },
	],
};
