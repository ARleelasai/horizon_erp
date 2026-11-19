frappe.query_reports["HML Production Cost Variance"] = {
	filters: [],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && ["variance", "variance_pct"].includes(column.fieldname) && data.variance > 0) {
			return `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
