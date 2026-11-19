frappe.query_reports["Inventory Obsolescence Analysis"] = {
	filters: [
		{ fieldname: "item_group", label: __("Category"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "days_threshold", label: __("Days Threshold"), fieldtype: "Int", default: 90 },
		{ fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "only_above_threshold", label: __("Only above threshold"), fieldtype: "Check" },
	],
	get_datatable_options(options) {
		return Object.assign(options, { checkboxColumn: true });
	},
	onload(report) {
		report.page.add_inner_button(__("Mark for Scrap"), () => {
			const dt = report.datatable;
			const checked = dt.rowmanager.getCheckedRows().map((i) => report.data[i]).filter((r) => r && r.item_code);
			if (!checked.length) {
				frappe.msgprint(__("Tick the rows to scrap first."));
				return;
			}
			frappe.prompt(
				[{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1,
					default: __("No sale for more than {0} days; physically inspected, not saleable.", [report.get_filter_value("days_threshold")]) }],
				(v) => {
					frappe
						.call("horizon_erp.horizon_erp.report.inventory_obsolescence_analysis.inventory_obsolescence_analysis.create_scrap_note", {
							rows: checked, reason: v.reason,
						})
						.then((r) => frappe.set_route("Form", "Scrap Note", r.message));
				},
				__("Create Scrap Note for {0} row(s)", [checked.length])
			);
		});
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && ["days_since_last_sale", "item_code"].includes(column.fieldname)) {
			if (data.aging === "red") return `<span style="color: var(--red-600); font-weight:600">${value}</span>`;
			if (data.aging === "yellow") return `<span style="color: #b7791f; font-weight:600">${value}</span>`;
		}
		return value;
	},
};
