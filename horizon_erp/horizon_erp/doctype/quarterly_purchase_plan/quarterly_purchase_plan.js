frappe.ui.form.on("Quarterly Purchase Plan", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Generate from Forecast"), () =>
				frm.call("generate").then(() => frm.reload_doc())
			);
		}
		if (!frm.is_new()) {
			frm.add_custom_button(__("Refresh Actual Orders"), () =>
				frm.call("refresh_actuals").then(() => frm.reload_doc())
			);
		}
	},
});
