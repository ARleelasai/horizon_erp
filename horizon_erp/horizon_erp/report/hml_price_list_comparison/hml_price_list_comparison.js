frappe.query_reports["HML Price List Comparison"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: "Horizon Manufacturing Ltd", reqd: 1 },
		{ fieldname: "item_group", label: __("Category"), fieldtype: "Link", options: "Item Group" },
		{
			fieldname: "price_date",
			label: __("Price As On"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			description: __("Set a date in Jan-Mar 2027 to see the Q4 Spares promotion."),
		},
		{ fieldname: "bulk_qty", label: __("Bulk Qty Scenario"), fieldtype: "Int", default: 60 },
	],
};
