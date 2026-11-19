"""BOM revision control, workstation capacity, make-to-stock Work Orders."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, nowdate

from horizon_erp.constants import COMPANY, WH_FG, WH_WIP, is_hml


def validate_bom(doc, method=None):
	"""Every BOM carries a revision number and a documented trigger."""
	if not is_hml(doc):
		return
	previous = frappe.get_all(
		"BOM",
		filters={"item": doc.item, "docstatus": 1, "name": ("!=", doc.name)},
		fields=["name", "hml_revision_no"],
		order_by="hml_revision_no desc, creation desc",
		limit=1,
	)
	if doc.is_new() or not doc.hml_revision_no:
		doc.hml_revision_no = (cint(previous[0].hml_revision_no) + 1) if previous else 1
		doc.hml_supersedes = previous[0].name if previous else None
	if not doc.hml_revision_reason:
		doc.hml_revision_reason = "Initial Release" if not previous else None
	if previous and (not doc.hml_revision_reason or doc.hml_revision_reason == "Initial Release"):
		frappe.throw(
			_("{0} already has BOM {1}. Select the Revision Trigger (design change, cost update, ...) for this new version.").format(
				doc.item, previous[0].name
			),
			title=_("Revision trigger required"),
		)
	if previous and not (doc.hml_revision_notes or "").strip():
		frappe.throw(_("Describe what changed in this revision (What Changed)."))


def validate_workstation(doc, method=None):
	if not doc.name.startswith("HML ") and not doc.workstation_name.startswith("HML "):
		return
	from horizon_erp.manufacturing.capacity import usable_hours_per_day

	hours = sum(flt(frappe.utils.time_diff_in_hours(w.end_time, w.start_time)) for w in doc.working_hours) or 16
	doc.hml_effective_hours_per_day = round(hours * (1 - flt(doc.hml_downtime_pct) / 100), 2)


def on_submit_sales_order(doc, method=None):
	"""Make-to-stock items: a submitted Sales Order raises a draft Work Order
	for the quantity free stock does not cover. Make-to-order items are left
	to the planner (Production Plan / manual WO with lead time)."""
	if not is_hml(doc) or doc.get("is_internal_customer"):
		return
	from horizon_erp.api.selling import sellable_warehouses

	warehouses = sellable_warehouses(doc.company)
	created = []
	for row in doc.items:
		item = frappe.get_cached_value("Item", row.item_code, ["hml_make_to_stock", "default_bom", "hml_mfg_lead_time_days"], as_dict=True)
		if not item or not item.hml_make_to_stock or not item.default_bom:
			continue
		# reserved_qty already includes this order, so a negative net position
		# is exactly the quantity stock cannot cover
		net = frappe.db.sql(
			"select sum(actual_qty - reserved_qty) from `tabBin` where item_code = %s and warehouse in %s",
			(row.item_code, tuple(warehouses)),
		)[0][0]
		shortfall = min(max(-flt(net), 0), flt(row.stock_qty))
		if shortfall <= 0:
			continue
		wo = frappe.get_doc(
			{
				"doctype": "Work Order",
				"company": doc.company,
				"production_item": row.item_code,
				"bom_no": item.default_bom,
				"qty": shortfall,
				"sales_order": doc.name,
				"sales_order_item": row.name,
				"use_multi_level_bom": 0,
				"wip_warehouse": WH_WIP,
				"fg_warehouse": WH_FG,
				"planned_start_date": f"{max(str(doc.transaction_date), nowdate())} 08:00:00",
				"expected_delivery_date": row.delivery_date,
				"hml_deadline": add_days(row.delivery_date or doc.delivery_date, -2),
				"description": _("Auto-created from {0} (make-to-stock item)").format(doc.name),
			}
		)
		wo.flags.ignore_permissions = True
		wo.get_items_and_operations_from_bom()
		try:
			wo.insert()
			created.append(wo.name)
		except frappe.ValidationError as e:
			# capacity conflict etc.: keep the order, tell the planner
			doc.add_comment("Comment", _("Auto Work Order for {0} not created: {1}").format(row.item_code, str(e)[:500]))
			frappe.clear_last_message()
	if created:
		doc.add_comment("Comment", _("Draft Work Order(s) created for make-to-stock items: {0}").format(", ".join(created)))
