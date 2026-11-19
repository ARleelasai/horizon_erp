// Horizon: Delivery Note - proof-of-delivery capture after dispatch.
frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		if (frm.doc.company !== "Horizon Manufacturing Ltd") return;
		if (frm.doc.docstatus === 1 && frm.doc.hml_pod_status === "Pending" && !frm.doc.is_return) {
			frm.add_custom_button(__("Record Proof of Delivery"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Proof of Delivery"),
					fields: [
						{ fieldname: "received_by", label: __("Received By"), fieldtype: "Data", reqd: 1 },
						{ fieldname: "received_on", label: __("Received On"), fieldtype: "Datetime", reqd: 1, default: frappe.datetime.now_datetime() },
						{ fieldname: "remarks", label: __("Remarks (damage, shortage)"), fieldtype: "Small Text" },
						{ fieldname: "signature", label: __("Customer Signature"), fieldtype: "Signature", reqd: 1 },
					],
					primary_action_label: __("Save"),
					primary_action(v) {
						frm.set_value({
							hml_received_by: v.received_by,
							hml_received_on: v.received_on,
							hml_customer_signature: v.signature,
							hml_pod_status: v.remarks ? "Received with Remarks" : "Received",
						});
						if (v.remarks) frm.set_value("hml_deviation_notes", (frm.doc.hml_deviation_notes || "") + "\nPOD: " + v.remarks);
						frm.save("Update");
						d.hide();
					},
				});
				d.show();
			});
		}
		if (frm.doc.hml_has_deviation) {
			frm.dashboard.add_comment(__("Delivered quantity differs from the open Sales Order quantity."), "orange", true);
		}
	},
});
