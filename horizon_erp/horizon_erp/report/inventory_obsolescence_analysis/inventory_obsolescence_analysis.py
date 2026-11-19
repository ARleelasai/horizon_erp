"""Inventory Obsolescence Analysis.

Per item and warehouse with stock: last purchase (receipt / purchase invoice
with stock), last sale (delivery / stock invoice to a customer), days since
last sale (since opening stock if never sold), value at cost. Rows older
than the threshold (default 90 days) are red, older than 30 yellow. A chart
shows the value by aging bucket. "Mark for Scrap" (report toolbar) turns the
selected rows into a draft Scrap Note for approval.
"""

import json

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

from horizon_erp.constants import COMPANY

GO_LIVE = "2026-04-01"
BUCKETS = [(0, 30, "0-30 d"), (31, 90, "31-90 d"), (91, 180, "91-180 d"), (181, 10**6, "180+ d")]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	threshold = int(filters.days_threshold or 90)
	today = getdate(filters.as_on_date or nowdate())
	wh_filters = {"company": COMPANY, "is_group": 0}
	if filters.warehouse:
		wh_filters["name"] = filters.warehouse
	warehouses = frappe.get_list("Warehouse", filters=wh_filters, pluck="name")
	rows = frappe.db.sql(
		"""
		select b.item_code, i.item_name, i.item_group, b.warehouse, b.actual_qty, b.stock_value, b.valuation_rate,
			(select max(sle.posting_date) from `tabStock Ledger Entry` sle where sle.item_code = b.item_code and sle.warehouse = b.warehouse
				and sle.is_cancelled = 0 and sle.actual_qty > 0 and sle.voucher_type in ('Purchase Receipt', 'Purchase Invoice')) last_purchase,
			(select max(sle.posting_date) from `tabStock Ledger Entry` sle
				left join `tabDelivery Note` dn on sle.voucher_type = 'Delivery Note' and dn.name = sle.voucher_no
				where sle.item_code = b.item_code and sle.is_cancelled = 0 and sle.actual_qty < 0
					and ((sle.voucher_type = 'Delivery Note' and ifnull(dn.is_internal_customer, 0) = 0) or sle.voucher_type = 'Sales Invoice')) last_sale,
			(select max(sle.posting_date) from `tabStock Ledger Entry` sle where sle.item_code = b.item_code and sle.warehouse = b.warehouse
				and sle.is_cancelled = 0 and sle.actual_qty < 0) last_issue
		from `tabBin` b join `tabItem` i on i.name = b.item_code
		where b.warehouse in %(wh)s and b.actual_qty > 0 {group}
		""".format(group="and i.item_group = %(item_group)s" if filters.item_group else ""),
		{"wh": tuple(warehouses) or ("",), "item_group": filters.item_group},
		as_dict=True,
	)
	data = []
	for r in rows:
		ref = r.last_sale or r.last_issue
		days = date_diff(today, ref) if ref else date_diff(today, GO_LIVE)
		if filters.only_above_threshold and days <= threshold:
			continue
		data.append(
			{
				"item_code": r.item_code, "item_name": r.item_name, "item_group": r.item_group, "warehouse": r.warehouse,
				"current_stock": r.actual_qty, "last_purchase": r.last_purchase, "last_sale": r.last_sale,
				"last_movement_out": r.last_issue, "days_since_last_sale": days, "inventory_value": r.stock_value,
				"valuation_rate": r.valuation_rate,
				"aging": "red" if days > threshold else ("yellow" if days > 30 else "green"),
				"never_sold": 0 if r.last_sale else 1,
			}
		)
	data.sort(key=lambda d: (-d["days_since_last_sale"], -flt(d["inventory_value"])))
	cols = [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 190},
		{"label": _("Category"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 130},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 180},
		{"label": _("Current Stock"), "fieldname": "current_stock", "fieldtype": "Float", "width": 100},
		{"label": _("Last Purchase"), "fieldname": "last_purchase", "fieldtype": "Date", "width": 105},
		{"label": _("Last Sale"), "fieldname": "last_sale", "fieldtype": "Date", "width": 95},
		{"label": _("Days Since Last Sale"), "fieldname": "days_since_last_sale", "fieldtype": "Int", "width": 120},
		{"label": _("Inventory Value (cost)"), "fieldname": "inventory_value", "fieldtype": "Currency", "width": 140},
		{"label": _("Never Sold"), "fieldname": "never_sold", "fieldtype": "Check", "width": 80},
	]
	buckets = {b[2]: 0 for b in BUCKETS}
	counts = {b[2]: 0 for b in BUCKETS}
	for d in data:
		label = next(b[2] for b in BUCKETS if b[0] <= d["days_since_last_sale"] <= b[1])
		buckets[label] += flt(d["inventory_value"])
		counts[label] += 1
	chart = {
		"data": {"labels": list(buckets), "datasets": [{"name": _("Items"), "values": list(counts.values())}]},
		"type": "bar",
		"colors": ["#e24c4c"],
		"title": _("Items by aging bucket"),
	}
	summary = [
		{"label": _("Value > {0} days").format(threshold), "value": sum(flt(d["inventory_value"]) for d in data if d["aging"] == "red"), "datatype": "Currency", "indicator": "Red"},
		{"label": _("Value 31-{0} days").format(threshold), "value": sum(flt(d["inventory_value"]) for d in data if d["aging"] == "yellow"), "datatype": "Currency", "indicator": "Yellow"},
		{"label": _("Items never sold since go-live"), "value": sum(d["never_sold"] for d in data), "indicator": "Orange"},
	]
	return cols, data, None, chart, summary


@frappe.whitelist()
def create_scrap_note(rows, reason):
	"""Selected report rows -> draft Scrap Note (approval happens on submit)."""
	frappe.has_permission("Scrap Note", "create", throw=True)
	rows = json.loads(rows) if isinstance(rows, str) else rows
	if not rows:
		frappe.throw(_("Select at least one row."))
	note = frappe.get_doc(
		{
			"doctype": "Scrap Note",
			"company": COMPANY,
			"reason": reason,
			"items": [
				{"item_code": r["item_code"], "warehouse": r["warehouse"], "qty": r["current_stock"],
					"days_since_last_sale": r.get("days_since_last_sale"), "disposition": "Scrap"}
				for r in rows
			],
		}
	)
	note.insert()
	return note.name
