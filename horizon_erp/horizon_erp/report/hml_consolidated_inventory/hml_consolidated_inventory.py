"""HML Consolidated Inventory.

One row per item, one quantity column per warehouse the viewer may see.
Warehouse visibility comes from frappe.get_list("Warehouse"), so User
Permissions apply: the Mumbai warehouse manager gets Mumbai columns only,
Finance and Operations get every HML warehouse.
"""

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.constants import COMPANY


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.company or COMPANY

	warehouses = get_visible_warehouses(filters)
	if not warehouses:
		return get_columns([]), [], _("You have no permitted warehouses for {0}").format(filters.company)

	data = get_data(filters, warehouses)
	columns = get_columns(warehouses)
	chart = get_chart(data, warehouses)
	summary = get_summary(data)
	return columns, data, None, chart, summary


def get_visible_warehouses(filters):
	wh_filters = {"company": filters.company, "is_group": 0, "disabled": 0}
	if filters.location:
		parent = frappe.db.get_value("Warehouse", filters.location, ["lft", "rgt"], as_dict=True)
		wh_filters.update({"lft": (">=", parent.lft), "rgt": ("<=", parent.rgt)})
	# get_list (not get_all) so that User Permissions on Warehouse are applied
	return frappe.get_list(
		"Warehouse",
		filters=wh_filters,
		fields=["name", "warehouse_name", "parent_warehouse"],
		order_by="lft",
	)


def get_data(filters, warehouses):
	names = [w.name for w in warehouses]
	conditions = {"warehouse": ("in", names)}
	bins = frappe.get_all(
		"Bin",
		filters=conditions,
		fields=[
			"item_code",
			"warehouse",
			"actual_qty",
			"reserved_qty",
			"projected_qty",
			"stock_value",
		],
	)

	items = {}
	item_filters = {"disabled": 0, "is_stock_item": 1}
	if filters.item_group:
		item_filters["item_group"] = filters.item_group
	meta = {
		d.name: d
		for d in frappe.get_all(
			"Item",
			filters=item_filters,
			fields=["name", "item_name", "item_group", "stock_uom", "hml_criticality"],
		)
	}

	reorder = {}
	for r in frappe.get_all(
		"Item Reorder", filters={"warehouse": ("in", names)}, fields=["parent", "warehouse_reorder_level"]
	):
		reorder[r.parent] = reorder.get(r.parent, 0) + flt(r.warehouse_reorder_level)

	for b in bins:
		if b.item_code not in meta:
			continue
		row = items.setdefault(
			b.item_code,
			frappe._dict(
				item_code=b.item_code,
				item_name=meta[b.item_code].item_name,
				item_group=meta[b.item_code].item_group,
				uom=meta[b.item_code].stock_uom,
				criticality=meta[b.item_code].hml_criticality,
				total_qty=0,
				reserved_qty=0,
				projected_qty=0,
				stock_value=0,
				reorder_level=reorder.get(b.item_code, 0),
			),
		)
		row[scrub_wh(b.warehouse)] = flt(b.actual_qty)
		row.total_qty += flt(b.actual_qty)
		row.reserved_qty += flt(b.reserved_qty)
		row.projected_qty += flt(b.projected_qty)
		row.stock_value += flt(b.stock_value)

	rows = sorted(items.values(), key=lambda r: (r.item_group, r.item_code))
	if not filters.include_zero:
		rows = [r for r in rows if r.total_qty or r.reserved_qty]
	for r in rows:
		r.below_reorder = 1 if r.reorder_level and r.projected_qty < r.reorder_level else 0
	return rows


def scrub_wh(name):
	return "wh_" + frappe.scrub(name)


def get_columns(warehouses):
	cols = [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Category"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 130},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 60},
	]
	for w in warehouses:
		cols.append(
			{
				"label": w.warehouse_name,
				"fieldname": scrub_wh(w.name),
				"fieldtype": "Float",
				"width": 120,
			}
		)
	cols += [
		{"label": _("Total Qty"), "fieldname": "total_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Reserved (SO)"), "fieldname": "reserved_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Projected Qty"), "fieldname": "projected_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Reorder Level"), "fieldname": "reorder_level", "fieldtype": "Float", "width": 110},
		{"label": _("Below Reorder"), "fieldname": "below_reorder", "fieldtype": "Check", "width": 100},
		{"label": _("Stock Value"), "fieldname": "stock_value", "fieldtype": "Currency", "width": 130},
	]
	return cols


def get_chart(data, warehouses):
	labels = [w.warehouse_name for w in warehouses]
	values = []
	for w in warehouses:
		key = scrub_wh(w.name)
		values.append(sum(flt(r.get(key)) for r in data))
	return {
		"data": {"labels": labels, "datasets": [{"name": _("Qty on hand"), "values": values}]},
		"type": "bar",
		"colors": ["#2e6bc6"],
	}


def get_summary(data):
	return [
		{"label": _("Items in stock"), "value": len([r for r in data if r.total_qty > 0]), "indicator": "Blue"},
		{
			"label": _("Below reorder level"),
			"value": len([r for r in data if r.below_reorder]),
			"indicator": "Red",
		},
		{
			"label": _("Stock value"),
			"value": sum(r.stock_value for r in data),
			"datatype": "Currency",
			"indicator": "Green",
		},
	]
