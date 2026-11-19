frappe.query_reports["HML Consolidated Inventory"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: "Horizon Manufacturing Ltd",
			reqd: 1,
		},
		{
			fieldname: "location",
			label: __("Location (warehouse group)"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => ({
				filters: { is_group: 1, company: frappe.query_report.get_filter_value("company") },
			}),
		},
		{
			fieldname: "item_group",
			label: __("Category"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "include_zero",
			label: __("Include zero-stock items"),
			fieldtype: "Check",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.below_reorder && ["projected_qty", "item_code"].includes(column.fieldname)) {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
