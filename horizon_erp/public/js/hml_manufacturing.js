// Horizon: Work Order capacity banner, Production Plan sequencing shortcut.
frappe.ui.form.on("Work Order", {
	refresh(frm) {
		if (frm.doc.company !== "Horizon Manufacturing Ltd") return;
		const d = frm.doc;
		if (d.hml_required_hours) {
			const ok = d.hml_capacity_status === "OK";
			frm.dashboard.add_comment(
				`${d.hml_production_line || ""}: needs <b>${d.hml_required_hours} h</b>, ` +
					`<b>${d.hml_line_free_hours} h</b> free before ${frappe.datetime.str_to_user(d.hml_deadline)}. ` +
					(ok ? "Capacity OK." : `Over capacity - decision: <b>${d.hml_capacity_decision}</b>.`),
				ok ? "green" : "orange",
				true
			);
		}
		if (d.hml_audit_hold) {
			frm.dashboard.add_comment(__("On hold: a production audit scored below 70. Close its corrective action before completing."), "red", true);
		}
		frm.add_custom_button(__("Line Schedule"), () =>
			frappe.set_route("query-report", "HML Production Schedule", { line: d.hml_production_line })
		, __("View"));
	},
});

frappe.ui.form.on("Production Plan", {
	refresh(frm) {
		if (frm.doc.company !== "Horizon Manufacturing Ltd") return;
		frm.add_custom_button(__("Suggest Sequence"), () => frappe.set_route("query-report", "HML Production Schedule"));
	},
});
