// Horizon: Quotation and Sales Order helpers.
// - When an item is picked (or qty changes) fetch free stock, BOM cost and the
//   estimated delivery date from horizon_erp.api.selling.get_item_planning_info.
//   Price list rate itself is filled by standard ERPNext pricing.
// - Show a stock / lead-time summary and the discount-approval state.
// Server-side validate recomputes all of this, so the browser is never trusted.

const HML_COMPANY = "Horizon Manufacturing Ltd";

function hml_is_hml(frm) {
	return frm.doc.company === HML_COMPANY;
}

function hml_fetch_planning(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!hml_is_hml(frm) || !row.item_code) return;
	frappe
		.call({
			method: "horizon_erp.api.selling.get_item_planning_info",
			args: {
				item_code: row.item_code,
				qty: row.stock_qty || row.qty || 1,
				company: frm.doc.company,
				transaction_date: frm.doc.transaction_date,
			},
		})
		.then((r) => {
			const info = r.message || {};
			frappe.model.set_value(cdt, cdn, {
				hml_available_qty: info.available_qty,
				hml_bom: info.bom,
				hml_unit_cost: info.unit_cost,
				hml_lead_time_days: info.lead_time_days,
				hml_estimated_delivery_date: info.estimated_delivery_date,
				hml_estimate_basis: info.basis,
			});
			if (frm.doctype === "Sales Order" && !row.delivery_date) {
				frappe.model.set_value(cdt, cdn, "delivery_date", info.estimated_delivery_date);
			}
			hml_show_stock(frm, row, info);
			hml_refresh_header_estimate(frm);
		});
}

function hml_show_stock(frm, row, info) {
	const lines = (info.warehouse_breakup || [])
		.map((b) => `${b.warehouse.replace(" - HML", "")}: <b>${b.free_qty}</b> free`)
		.join(" &middot; ");
	const color = info.available_qty >= (row.qty || 0) ? "green" : "orange";
	frappe.show_alert(
		{
			message: `${row.item_code}: ${info.available_qty} free. ${lines || "No stock"}<br>${info.basis}`,
			indicator: color,
		},
		8
	);
}

function hml_refresh_header_estimate(frm) {
	const dates = (frm.doc.items || []).map((r) => r.hml_estimated_delivery_date).filter(Boolean).sort();
	if (dates.length) frm.set_value("hml_estimated_delivery_date", dates[dates.length - 1]);
}

function hml_pricing_banner(frm) {
	if (!hml_is_hml(frm)) return;
	const d = frm.doc;
	if (d.hml_needs_discount_approval) {
		const why = d.hml_below_cost ? "a line is priced below standard cost" : `effective discount ${d.hml_effective_discount_pct}% exceeds 15%`;
		frm.dashboard.set_headline_alert(
			`<span class="indicator orange">Discount approval required: ${why}.</span>`
		);
	} else if (d.hml_effective_discount_pct) {
		frm.dashboard.set_headline_alert(
			`<span class="indicator green">Within discount policy (${d.hml_effective_discount_pct}% effective).</span>`
		);
	}
	if (frm.doctype === "Sales Order" && d.hml_delivery_risk) {
		frm.dashboard.add_comment(
			`Promised delivery ${frappe.datetime.str_to_user(d.delivery_date)} is before the earliest achievable date ` +
				`${frappe.datetime.str_to_user(d.hml_estimated_delivery_date)}. Agree a date with the customer or ship partial.`,
			"red",
			true
		);
	}
}

["Quotation", "Sales Order"].forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			hml_pricing_banner(frm);
			if (hml_is_hml(frm) && frm.doc.docstatus === 0) {
				frm.add_custom_button(__("Refresh Availability"), () => {
					(frm.doc.items || []).forEach((r) => hml_fetch_planning(frm, r.doctype, r.name));
				});
			}
		},
		company(frm) {
			hml_pricing_banner(frm);
		},
	});
	frappe.ui.form.on(`${doctype} Item`, {
		item_code(frm, cdt, cdn) {
			// let standard get_item_details finish first
			setTimeout(() => hml_fetch_planning(frm, cdt, cdn), 600);
		},
		qty(frm, cdt, cdn) {
			hml_fetch_planning(frm, cdt, cdn);
		},
	});
});
