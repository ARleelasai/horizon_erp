frappe.query_reports["HML Order Fulfilment Status"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: "Horizon Manufacturing Ltd", reqd: 1 },
		{ fieldname: "from_date", label: __("Order From"), fieldtype: "Date", default: "2026-04-01" },
		{ fieldname: "to_date", label: __("Order To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "as_on_date", label: __("As On"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "branch", label: __("Location"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "only_pending", label: __("Only open lines"), fieldtype: "Check", default: 0 },
		{ fieldname: "only_overdue", label: __("Only overdue > 5 days"), fieldtype: "Check", default: 0 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (data.overdue_flag && ["sales_order", "days_overdue", "delivery_date"].includes(column.fieldname)) {
			return `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		if (column.fieldname === "fulfilment") {
			const color = { Completed: "green", "Partially Delivered": "orange", "Not Delivered": "red" }[data.fulfilment] || "blue";
			return `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return value;
	},
};
