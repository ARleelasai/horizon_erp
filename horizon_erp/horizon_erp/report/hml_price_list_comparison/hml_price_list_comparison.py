"""HML Price List Comparison.

For every sellable item: list price per region (price list) and the net price
a customer actually gets per customer group, after the pricing rule that wins
under the precedence policy (highest priority wins, no stacking - D-06).

Scenario columns are computed with ERPNext's own pricing-rule engine, so the
report shows exactly what a Quotation would charge.
"""

import frappe
from erpnext.accounts.doctype.pricing_rule.pricing_rule import get_pricing_rule_for_item
from frappe import _
from frappe.utils import flt, getdate, nowdate

from horizon_erp.constants import COMPANY

REGIONS = [
	("West", "HML Standard Selling", "Maharashtra"),
	("North", "HML North Region Selling", "Delhi NCR"),
]
GROUPS = ["Standard", "Premium"]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.company or COMPANY
	on_date = getdate(filters.price_date or nowdate())
	bulk_qty = int(filters.bulk_qty or 60)

	items = frappe.get_all(
		"Item",
		filters={"is_sales_item": 1, "disabled": 0, **({"item_group": filters.item_group} if filters.item_group else {})},
		fields=["name", "item_name", "item_group"],
		order_by="item_group, name",
	)
	prices = {}
	for p in frappe.get_all(
		"Item Price",
		filters={"price_list": ("in", [r[1] for r in REGIONS]), "item_code": ("in", [i.name for i in items] or [""])},
		fields=["item_code", "price_list", "price_list_rate"],
	):
		prices[(p.item_code, p.price_list)] = flt(p.price_list_rate)

	data = []
	for item in items:
		row = {"item_code": item.name, "item_name": item.item_name, "item_group": item.item_group}
		if not any((item.name, r[1]) in prices for r in REGIONS):
			continue
		for region, price_list, territory in REGIONS:
			list_rate = prices.get((item.name, price_list))
			row[f"list_{region}"] = list_rate
			if not list_rate:
				continue
			for group in GROUPS:
				for qty, suffix in ((1, ""), (bulk_qty, "_bulk")):
					disc, rule = _discount(item, group, territory, price_list, qty, on_date, filters.company, list_rate)
					row[f"{region}_{group}{suffix}"] = round(list_rate * (1 - disc / 100), 2)
					if rule and suffix == "" and group == "Premium":
						row[f"rule_{region}"] = rule
		data.append(row)
	return get_columns(bulk_qty), data


def _discount(item, customer_group, territory, price_list, qty, on_date, company, list_rate):
	args = frappe._dict(
		{
			"item_code": item.name,
			"item_group": item.item_group,
			"customer_group": customer_group,
			"territory": territory,
			"price_list": price_list,
			"selling_price_list": price_list,
			"qty": qty,
			"stock_qty": qty,
			"transaction_date": on_date,
			"company": company,
			"doctype": "Quotation",
			"transaction_type": "selling",
			"price_list_rate": list_rate,
			"currency": "INR",
			"conversion_rate": 1,
			"plc_conversion_rate": 1,
			"conversion_factor": 1,
			"name": None,
			"child_docname": None,
		}
	)
	res = get_pricing_rule_for_item(args, doc=None, for_validate=False)
	disc = flt(res.get("discount_percentage"))
	return disc, res.get("pricing_rules")


def get_columns(bulk_qty):
	cols = [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 190},
		{"label": _("Category"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 110},
	]
	for region, _pl, _t in REGIONS:
		cols.append({"label": _("{0} List").format(region), "fieldname": f"list_{region}", "fieldtype": "Currency", "width": 110})
		for group in GROUPS:
			cols.append({"label": f"{region} {group}", "fieldname": f"{region}_{group}", "fieldtype": "Currency", "width": 115})
			cols.append(
				{"label": f"{region} {group} x{bulk_qty}", "fieldname": f"{region}_{group}_bulk", "fieldtype": "Currency", "width": 125}
			)
	return cols
