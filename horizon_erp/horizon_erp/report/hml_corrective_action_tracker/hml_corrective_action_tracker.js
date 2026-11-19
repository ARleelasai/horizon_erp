frappe.query_reports["HML Corrective Action Tracker"] = {
	filters: [
		{ fieldname: "owner_user", label: __("Owner"), fieldtype: "Link", options: "User" },
		{ fieldname: "include_closed", label: __("Include completed / verified"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "bucket") {
			const c = { Overdue: "red", "Due in 7 days": "orange", Open: "blue", Closed: "green" }[data.bucket];
			return `<span class="indicator-pill ${c}">${value}</span>`;
		}
		return value;
	},
};
