// Production Audit: score slider with colour bands, Work Order context panel,
// photo mandatory below 70 (also enforced on the server).
const HML_BANDS = [
	{ max: 69, color: "#e24c4c", label: "Critical - escalates to Operations Head" },
	{ max: 84, color: "#f0ad4e", label: "Attention" },
	{ max: 100, color: "#28a745", label: "Good" },
];

function hml_band(score) {
	return HML_BANDS.find((b) => score <= b.max) || HML_BANDS[2];
}

function hml_render_slider(frm) {
	const score = cint(frm.doc.audit_score);
	const band = hml_band(score);
	const disabled = frm.doc.docstatus !== 0 ? "disabled" : "";
	frm.fields_dict.score_slider.$wrapper.html(`
		<div style="padding: 8px 0">
			<input type="range" min="0" max="100" step="1" value="${score}" ${disabled}
				class="hml-score-range" style="width: 100%; accent-color: ${band.color}">
			<div style="display:flex; justify-content:space-between; font-size: 12px; color: var(--text-muted)">
				<span>0</span><span style="color:#e24c4c">70</span><span style="color:#f0ad4e">85</span><span>100</span>
			</div>
			<div class="hml-score-label" style="margin-top:6px; font-weight:600; color:${band.color}">
				${score} - ${band.label}
			</div>
		</div>`);
	frm.fields_dict.score_slider.$wrapper.find(".hml-score-range").on("input change", function () {
		frm.set_value("audit_score", cint(this.value));
	});
}

function hml_render_context(frm) {
	if (!frm.doc.work_order) {
		frm.fields_dict.wo_context.$wrapper.html("");
		return;
	}
	frappe
		.call("horizon_erp.horizon_erp.doctype.production_audit.production_audit.get_work_order_context", {
			work_order: frm.doc.work_order,
		})
		.then((r) => {
			const wo = r.message;
			if (!wo) return;
			const prev = (wo.previous_audits || [])
				.map((a) => `${frappe.datetime.str_to_user(a.audit_date)}: <b style="color:${hml_band(a.audit_score).color}">${a.audit_score}</b>`)
				.join(" &middot; ");
			frm.fields_dict.wo_context.$wrapper.html(`
				<div class="alert ${wo.hml_audit_hold ? "alert-danger" : "alert-info"}" style="margin-bottom: 0">
					<b>${wo.name}</b> &middot; ${wo.production_item} (${wo.item_name})<br>
					Machine / line: <b>${wo.hml_production_line || "not assigned"}</b> &middot;
					Qty ${wo.produced_qty} / ${wo.qty} &middot; Status ${wo.status}
					${wo.sales_order ? " &middot; SO " + wo.sales_order : ""}
					${wo.hml_deadline ? " &middot; due " + frappe.datetime.str_to_user(wo.hml_deadline) : ""}
					${wo.hml_audit_hold ? "<br><b>On hold: a previous audit scored below 70.</b>" : ""}
					${prev ? "<br>Previous audits: " + prev : ""}
				</div>`);
		});
}

frappe.ui.form.on("Production Audit", {
	refresh(frm) {
		hml_render_slider(frm);
		hml_render_context(frm);
		frm.toggle_reqd("photo_1", cint(frm.doc.audit_score) < 70);
	},
	work_order(frm) {
		hml_render_context(frm);
	},
	audit_score(frm) {
		const score = cint(frm.doc.audit_score);
		if (score < 0 || score > 100) {
			frappe.msgprint(__("Audit Score must be between 0 and 100."));
			frm.set_value("audit_score", Math.max(0, Math.min(100, score)));
			return;
		}
		frm.toggle_reqd("photo_1", score < 70);
		const band = hml_band(score);
		const $w = frm.fields_dict.score_slider.$wrapper;
		$w.find(".hml-score-range").val(score).css("accent-color", band.color);
		$w.find(".hml-score-label").css("color", band.color).text(`${score} - ${band.label}`);
	},
	before_submit(frm) {
		if (cint(frm.doc.audit_score) < 70 && !frm.doc.photo_1) {
			frappe.throw(__("Upload at least one photo: score is below 70."));
		}
	},
});
