"""HML BOM Explosion - full material requirement for N finished units.

Walks the BOM tree through every sub-assembly's default BOM (3 levels for the
HX-500 / CX-200). For each line: quantity for the requested build, stock
available, shortfall, lead time (purchase lead time for bought items,
manufacturing lead time for made items) and projected cost at current
valuation. Operation rows show line hours and operating cost per level.

Summary: total material + operating cost, and the critical path = the longest
chain of (component lead time + manufacturing lead times above it).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from horizon_erp.api.selling import sellable_warehouses


def execute(filters=None):
	filters = frappe._dict(filters or {})
	bom = filters.bom or frappe.db.get_value("Item", filters.item_code or "HX-500", "default_bom")
	if not bom:
		frappe.throw(_("Select a BOM or an item with a default BOM."))
	qty = flt(filters.qty) or 1
	company = frappe.db.get_value("BOM", bom, "company")
	warehouses = sellable_warehouses(company)
	stock = {
		r.item_code: flt(r.qty)
		for r in frappe.db.sql(
			"select item_code, sum(actual_qty - reserved_qty_for_production) qty from `tabBin` where warehouse in %s group by item_code",
			(tuple(warehouses),),
			as_dict=True,
		)
	}
	data, totals = [], {"material": 0, "operating": 0, "critical": 0, "critical_item": None}
	walk(bom, qty, 0, data, totals, stock, upstream_lead=0, show_ops=not filters.hide_operations)
	columns = get_columns()
	summary = [
		{"label": _("Material cost"), "value": totals["material"], "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Operating cost"), "value": totals["operating"], "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Projected total"), "value": totals["material"] + totals["operating"], "datatype": "Currency", "indicator": "Green"},
		{"label": _("Critical path (days)"), "value": totals["critical"], "indicator": "Red"},
		{"label": _("Critical item"), "value": totals["critical_item"] or "-", "datatype": "Data", "indicator": "Red"},
	]
	return columns, data, None, None, summary


def walk(bom, qty, level, data, totals, stock, upstream_lead, show_ops):
	doc = frappe.get_cached_doc("BOM", bom)
	per = qty / flt(doc.quantity or 1)
	mfg_lead = cint(frappe.get_cached_value("Item", doc.item, "hml_mfg_lead_time_days"))
	if show_ops:
		for op in doc.operations:
			hours = flt(op.time_in_mins) * per / 60
			cost = hours * flt(op.hour_rate)
			totals["operating"] += cost
			data.append(
				{
					"indent": level + 1,
					"level": level + 1,
					"item_code": f"[op] {op.operation}",
					"description": f"{op.workstation} - {hours:.2f} h",
					"total_qty": round(hours, 2),
					"uom": "Hour",
					"unit_cost": op.hour_rate,
					"amount": cost,
					"source": "Operation",
				}
			)
	for row in doc.items:
		need = flt(row.stock_qty) * per
		child_bom = frappe.db.get_value("Item", row.item_code, "default_bom")
		made = bool(child_bom)
		lead = cint(frappe.get_cached_value("Item", row.item_code, "hml_mfg_lead_time_days" if made else "lead_time_days"))
		available = stock.get(row.item_code, 0)
		unit_cost = flt(frappe.db.get_value("BOM", child_bom, "total_cost")) if made else flt(row.rate)
		line = {
			"indent": level + 1,
			"level": level + 1,
			"item_code": row.item_code,
			"description": row.item_name,
			"qty_per_unit": flt(row.stock_qty) / flt(doc.quantity or 1),
			"total_qty": need,
			"uom": row.stock_uom,
			"available": available,
			"shortfall": max(need - available, 0),
			"lead_time": lead,
			"cumulative_lead": upstream_lead + mfg_lead + lead,
			"unit_cost": unit_cost,
			"amount": unit_cost * need,
			"source": "Make" if made else "Buy",
			"bom": child_bom,
		}
		data.append(line)
		if made:
			walk(child_bom, need, level + 1, data, totals, stock, upstream_lead + mfg_lead, show_ops)
		else:
			totals["material"] += line["amount"]
			if line["cumulative_lead"] > totals["critical"]:
				totals["critical"] = line["cumulative_lead"]
				totals["critical_item"] = row.item_code


def get_columns():
	return [
		{"label": _("Item / Operation"), "fieldname": "item_code", "fieldtype": "Data", "width": 200},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 220},
		{"label": _("Level"), "fieldname": "level", "fieldtype": "Int", "width": 55},
		{"label": _("Make / Buy"), "fieldname": "source", "fieldtype": "Data", "width": 85},
		{"label": _("Qty per Unit"), "fieldname": "qty_per_unit", "fieldtype": "Float", "width": 95},
		{"label": _("Total Qty"), "fieldname": "total_qty", "fieldtype": "Float", "width": 90},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 60},
		{"label": _("Available"), "fieldname": "available", "fieldtype": "Float", "width": 90},
		{"label": _("Shortfall"), "fieldname": "shortfall", "fieldtype": "Float", "width": 85},
		{"label": _("Lead Time (d)"), "fieldname": "lead_time", "fieldtype": "Int", "width": 95},
		{"label": _("Cumulative Lead (d)"), "fieldname": "cumulative_lead", "fieldtype": "Int", "width": 120},
		{"label": _("Unit Cost"), "fieldname": "unit_cost", "fieldtype": "Currency", "width": 110},
		{"label": _("Projected Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
		{"label": _("BOM"), "fieldname": "bom", "fieldtype": "Link", "options": "BOM", "width": 150},
	]
