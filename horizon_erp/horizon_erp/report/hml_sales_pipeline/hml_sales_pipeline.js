frappe.query_reports["HML Sales Pipeline"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: "Horizon Manufacturing Ltd", reqd: 1 },
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: ["Open Pipeline", "Leads by Status and Age", "Quote Conversion"],
			default: "Open Pipeline",
			reqd: 1,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "health" && data) {
			const color = data.health === "Healthy" ? "green" : data.health.startsWith("Expiring") ? "orange" : "red";
			return `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return value;
	},
};
