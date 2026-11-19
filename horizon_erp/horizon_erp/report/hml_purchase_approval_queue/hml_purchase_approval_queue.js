frappe.query_reports["HML Purchase Approval Queue"] = {
	filters: [
		{
			fieldname: "state",
			label: __("State"),
			fieldtype: "Select",
			options: ["", "Pending Dept Head", "Pending Procurement", "Pending Finance Director"],
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "sla") {
			const color = data.sla === "Within SLA" ? "green" : data.sla.startsWith("Breached") ? "red" : "red";
			return `<span class="indicator-pill ${color}">${value}</span>`;
		}
		if (data && data.hours_pending > 24 && ["purchase_order", "hours_pending"].includes(column.fieldname)) {
			return `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
