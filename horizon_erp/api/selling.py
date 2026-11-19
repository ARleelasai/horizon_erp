"""Selling helpers: availability, BOM cost and delivery-date estimate.

`get_item_planning_info` is whitelisted for the Quotation / Sales Order client
script and is also called server-side on validate, so the value saved on the
document never depends on the browser.

Estimate rules (documented in the design doc, section Selling):
* Enough free stock across sellable HML warehouses -> ship in DISPATCH_DAYS.
* Otherwise, manufactured item (has default BOM): the shortfall is produced.
  Delivery = longest lead time of any component that is itself short
  + item manufacturing lead time + DISPATCH_DAYS.
* Otherwise, bought item: purchase lead time + DISPATCH_DAYS.
Calendar days are used; the capacity check on Work Orders (Phase 4) is the
place where line load is considered.
"""

import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from horizon_erp.constants import COMPANY, WH_QC, WH_REJECTED, WH_SCRAP, WH_TRANSIT, WH_WIP

DISPATCH_DAYS = 2
NON_SELLABLE = {WH_WIP, WH_QC, WH_REJECTED, WH_SCRAP, WH_TRANSIT}


def sellable_warehouses(company=COMPANY):
	return [
		w
		for w in frappe.get_all("Warehouse", filters={"company": company, "is_group": 0, "disabled": 0}, pluck="name")
		if w not in NON_SELLABLE
	]


def free_stock(item_code, warehouses):
	if not warehouses:
		return 0, []
	rows = frappe.get_all(
		"Bin",
		filters={"item_code": item_code, "warehouse": ("in", warehouses)},
		fields=["warehouse", "actual_qty", "reserved_qty"],
	)
	breakup = [
		{"warehouse": r.warehouse, "actual_qty": flt(r.actual_qty), "free_qty": flt(r.actual_qty) - flt(r.reserved_qty)}
		for r in rows
		if flt(r.actual_qty)
	]
	return max(sum(b["free_qty"] for b in breakup), 0), breakup


def unit_cost(item_code, bom=None):
	if bom:
		cost = frappe.db.get_value("BOM", bom, ["total_cost", "quantity"], as_dict=True)
		if cost and flt(cost.quantity):
			return flt(cost.total_cost) / flt(cost.quantity)
	return flt(frappe.db.get_value("Item", item_code, "valuation_rate"))


@frappe.whitelist()
def get_item_planning_info(item_code, qty=1, company=None, transaction_date=None):
	company = company or COMPANY
	qty = flt(qty) or 1
	start = getdate(transaction_date or nowdate())
	item = frappe.get_cached_value(
		"Item", item_code, ["lead_time_days", "hml_mfg_lead_time_days", "default_bom", "is_stock_item"], as_dict=True
	)
	if not item:
		frappe.throw(f"Item {item_code} not found")

	warehouses = sellable_warehouses(company)
	available, breakup = free_stock(item_code, warehouses)
	bom = item.default_bom or frappe.db.get_value("BOM", {"item": item_code, "is_default": 1, "is_active": 1, "docstatus": 1})

	if not item.is_stock_item or available >= qty:
		lead = 0
		basis = f"In stock ({available:g} free) - ships in {DISPATCH_DAYS} days"
	elif bom:
		shortfall = qty - available
		component_lead, short_components = _component_lead_time(bom, shortfall, warehouses)
		lead = component_lead + cint(item.hml_mfg_lead_time_days)
		basis = (
			f"Make {shortfall:g}: manufacturing {cint(item.hml_mfg_lead_time_days)} d"
			+ (f" + components {component_lead} d ({', '.join(short_components[:3])})" if component_lead else " (components in stock)")
			+ f" + dispatch {DISPATCH_DAYS} d"
		)
	else:
		lead = cint(item.lead_time_days)
		basis = f"Buy {qty - available:g}: supplier lead time {lead} d + dispatch {DISPATCH_DAYS} d"

	return {
		"available_qty": available,
		"warehouse_breakup": breakup,
		"bom": bom,
		"unit_cost": unit_cost(item_code, bom),
		"lead_time_days": lead,
		"estimated_delivery_date": add_days(start, lead + DISPATCH_DAYS),
		"basis": basis,
	}


def _component_lead_time(bom, make_qty, warehouses):
	"""Longest purchase lead time among exploded components that are short."""
	bom_doc = frappe.get_cached_doc("BOM", bom)
	per_unit = 1 / flt(bom_doc.quantity or 1)
	longest, short = 0, []
	for row in bom_doc.exploded_items:
		need = flt(row.stock_qty) * per_unit * make_qty
		have, _ = free_stock(row.item_code, warehouses)
		if have < need:
			lt = cint(frappe.get_cached_value("Item", row.item_code, "lead_time_days"))
			short.append(row.item_code)
			longest = max(longest, lt)
	return longest, short
