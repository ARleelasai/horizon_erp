"""HML Product Profitability - contribution margin by product.

Revenue = invoiced net value (non-return, non-internal invoices).
Variable cost = cost of goods sold from the stock ledger of the deliveries
(materials + conversion cost absorbed through BOM operations / job cards).
Contribution = revenue - variable cost; CM % = contribution / revenue.
Data gaps (documented): freight-out and warranty are not yet tagged to
items, so they are not deducted here.
"""

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.constants import COMPANY


def product_rows(from_date, to_date):
	rev = frappe.db.sql(
		"""select sii.item_code, sii.item_name, i.item_group, sum(sii.stock_qty) qty, sum(sii.base_net_amount) revenue
		from `tabSales Invoice Item` sii join `tabSales Invoice` si on si.name = sii.parent join `tabItem` i on i.name = sii.item_code
		where si.company = %s and si.docstatus = 1 and si.is_return = 0 and ifnull(si.is_internal_customer, 0) = 0
			and si.posting_date between %s and %s and i.is_fixed_asset = 0
		group by sii.item_code""",
		(COMPANY, from_date, to_date), as_dict=True)
	cogs = {
		r.item_code: flt(r.cost)
		for r in frappe.db.sql(
			"""select sle.item_code, -sum(sle.stock_value_difference) cost from `tabStock Ledger Entry` sle
			join `tabDelivery Note` dn on dn.name = sle.voucher_no and sle.voucher_type = 'Delivery Note'
			where sle.company = %s and sle.is_cancelled = 0 and ifnull(dn.is_internal_customer, 0) = 0 and dn.is_return = 0
				and sle.posting_date between %s and %s group by sle.item_code""",
			(COMPANY, from_date, to_date), as_dict=True)
	}
	for r in rev:
		r.cost = cogs.get(r.item_code, 0)
		r.contribution = flt(r.revenue) - r.cost
		r.cm_pct = r.contribution / flt(r.revenue) * 100 if r.revenue else 0
	return rev


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = sorted(product_rows(filters.from_date or "2026-04-01", filters.to_date or "2027-03-31"), key=lambda r: -r.cm_pct)
	top = rows[: int(filters.top or 10)]
	cols = [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Category"), "fieldname": "item_group", "fieldtype": "Data", "width": 110},
		{"label": _("Qty Sold"), "fieldname": "qty", "fieldtype": "Float", "width": 80},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 120},
		{"label": _("Variable Cost (COGS)"), "fieldname": "cost", "fieldtype": "Currency", "width": 140},
		{"label": _("Contribution"), "fieldname": "contribution", "fieldtype": "Currency", "width": 120},
		{"label": _("CM %"), "fieldname": "cm_pct", "fieldtype": "Percent", "width": 80},
	]
	chart = {"data": {"labels": [r.item_code for r in top], "datasets": [{"name": "CM %", "values": [round(r.cm_pct, 1) for r in top]}]}, "type": "bar"}
	return cols, top, None, chart
