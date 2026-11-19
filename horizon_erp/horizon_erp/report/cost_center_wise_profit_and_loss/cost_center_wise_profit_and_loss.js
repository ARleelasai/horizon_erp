frappe.query_reports["Cost Center Wise Profit and Loss"] = {
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
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default: "2026-2027",
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Up To"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "branch",
			label: __("Location (Branch)"),
			fieldtype: "Link",
			options: "Branch",
		},
	],
	tree: true,
	name_field: "cost_center",
	parent_field: "",
	initial_depth: 3,
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.bold) {
			value = `<b>${value}</b>`;
		}
		if (data && column.fieldtype === "Currency" && data.line === "Net Profit" && data[column.fieldname] < 0) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
