frappe.query_reports["HML Project Dashboard"] = {
	filters: [{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project", reqd: 0 }],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && ["hour_variance", "schedule_variance"].includes(column.fieldname) && data[column.fieldname] > 0) {
			return `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
