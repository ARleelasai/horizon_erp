"""HML Inventory Health.

Per item and warehouse:
* Below reorder level      -> red      (projected qty < Item Reorder level)
* No movement > 90 days    -> yellow   (last outward/inward stock movement)
Per category (chart + summary): stock turnover = cost of goods issued in the
last 365 days / average stock value (today and 365 days ago).
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, nowdate

from horizon_erp.constants import COMPANY

AGING_DAYS = 90


def execute(filters=None):
	filters = frappe._dict(filters or {})
	today = getdate(filters.as_on_date or nowdate())
	warehouses = frappe.get_list("Warehouse", filters={"company": COMPANY, "is_group": 0}, pluck="name")
	bins = frappe.get_all(
		"Bin",
		filters={"warehouse": ("in", warehouses or [""])},
		fields=["item_code", "warehouse", "actual_qty", "projected_qty", "stock_value"],
	)
	reorder = {
		(r.parent, r.warehouse): flt(r.warehouse_reorder_level)
		for r in frappe.get_all("Item Reorder", fields=["parent", "warehouse", "warehouse_reorder_level"])
	}
	last_move = {
		(r.item_code, r.warehouse): r.last_date
		for r in frappe.db.sql(
			"""select item_code, warehouse, max(posting_date) last_date from `tabStock Ledger Entry`
			where company = %s and is_cancelled = 0 and voucher_type != 'Stock Reconciliation'
			group by item_code, warehouse""",
			COMPANY,
			as_dict=True,
		)
	}
	groups = dict(frappe.get_all("Item", fields=["name", "item_group"], as_list=True))
	data = []
	for b in bins:
		if not flt(b.actual_qty) and not reorder.get((b.item_code, b.warehouse)):
			continue
		level = reorder.get((b.item_code, b.warehouse), 0)
		last = last_move.get((b.item_code, b.warehouse))
		idle = date_diff(today, last) if last else date_diff(today, "2026-04-01")
		below = 1 if level and flt(b.projected_qty) < level else 0
		aging = 1 if flt(b.actual_qty) > 0 and idle > AGING_DAYS else 0
		status = "Below Reorder" if below else ("Aging > 90 d" if aging else "Healthy")
		if filters.only_exceptions and status == "Healthy":
			continue
		data.append(
			{
				"item_code": b.item_code,
				"item_group": groups.get(b.item_code),
				"warehouse": b.warehouse,
				"actual_qty": b.actual_qty,
				"projected_qty": b.projected_qty,
				"reorder_level": level,
				"stock_value": b.stock_value,
				"last_movement": last,
				"days_idle": idle,
				"status": status,
			}
		)
	data.sort(key=lambda d: ({"Below Reorder": 0, "Aging > 90 d": 1}.get(d["status"], 2), -flt(d["stock_value"])))
	turnover = turnover_by_category(today)
	columns = [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Category"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 130},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 190},
		{"label": _("On Hand"), "fieldname": "actual_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Projected"), "fieldname": "projected_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Reorder Level"), "fieldname": "reorder_level", "fieldtype": "Float", "width": 100},
		{"label": _("Stock Value"), "fieldname": "stock_value", "fieldtype": "Currency", "width": 120},
		{"label": _("Last Movement"), "fieldname": "last_movement", "fieldtype": "Date", "width": 110},
		{"label": _("Days Idle"), "fieldname": "days_idle", "fieldtype": "Int", "width": 80},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
	]
	chart = {
		"data": {"labels": [t["category"] for t in turnover], "datasets": [{"name": _("Turnover (x / year)"), "values": [t["turnover"] for t in turnover]}]},
		"type": "bar",
		"title": _("Stock turnover by category"),
	}
	summary = [
		{"label": _("Below reorder (red)"), "value": len([d for d in data if d["status"] == "Below Reorder"]), "indicator": "Red"},
		{"label": _("Aging > 90 days (yellow)"), "value": len([d for d in data if d["status"] == "Aging > 90 d"]), "indicator": "Yellow"},
		{
			"label": _("Value aging > 90 d"),
			"value": sum(flt(d["stock_value"]) for d in data if d["status"] == "Aging > 90 d"),
			"datatype": "Currency",
			"indicator": "Yellow",
		},
	] + [{"label": _("Turnover {0}").format(t["category"]), "value": t["turnover"], "indicator": "Blue"} for t in turnover[:4]]
	return columns, data, None, chart, summary


def turnover_by_category(today):
	year_ago = add_days(today, -365)
	issued = {
		r.item_group: flt(r.value)
		for r in frappe.db.sql(
			"""select i.item_group, -sum(sle.stock_value_difference) value
			from `tabStock Ledger Entry` sle join `tabItem` i on i.name = sle.item_code
			left join `tabDelivery Note` dn on sle.voucher_type = 'Delivery Note' and dn.name = sle.voucher_no
			where sle.company = %s and sle.is_cancelled = 0 and sle.actual_qty < 0
				and sle.posting_date between %s and %s
				and (sle.voucher_type in ('Stock Entry', 'Sales Invoice') or (sle.voucher_type = 'Delivery Note' and ifnull(dn.is_internal_customer, 0) = 0))
			group by i.item_group""",
			(COMPANY, year_ago, today),
			as_dict=True,
		)
	}
	stock_now = {
		r.item_group: flt(r.value)
		for r in frappe.db.sql(
			"""select i.item_group, sum(b.stock_value) value from `tabBin` b join `tabItem` i on i.name = b.item_code
			join `tabWarehouse` w on w.name = b.warehouse where w.company = %s group by i.item_group""",
			COMPANY,
			as_dict=True,
		)
	}
	out = []
	for group, now_value in stock_now.items():
		avg_stock = now_value  # opening was loaded on 1 Apr 2026, so today's value is the best average available
		out.append({"category": group, "turnover": round(issued.get(group, 0) / avg_stock, 2) if avg_stock else 0})
	return sorted(out, key=lambda t: -t["turnover"])
