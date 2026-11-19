frappe.query_reports["HML Net Party Position"] = {
	filters: [],
	onload(report) {
		report.page.add_inner_button(__("Create Contra Entry"), () => {
			const rows = (report.data || []).filter((r) => r.linked && r.settle_off > 0);
			if (!rows.length) return frappe.msgprint(__("Nothing to set off."));
			frappe.prompt(
				[
					{ fieldname: "pair", label: __("Party"), fieldtype: "Select", reqd: 1, options: rows.map((r) => `${r.customer} / ${r.supplier}`).join("\n") },
					{ fieldname: "amount", label: __("Amount agreed with the party"), fieldtype: "Currency", reqd: 1 },
					{ fieldname: "remark", label: __("Reference (settlement letter / email)"), fieldtype: "Data" },
				],
				(v) => {
					const [customer, supplier] = v.pair.split(" / ");
					frappe.call("horizon_erp.strategy.parties.create_contra_entry", { customer, supplier, amount: v.amount, remark: v.remark })
						.then((r) => frappe.set_route("Form", "Journal Entry", r.message));
				},
				__("Net settlement (draft Journal Entry)")
			);
		});
	},
};
