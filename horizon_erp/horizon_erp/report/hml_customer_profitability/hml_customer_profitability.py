"""HML Customer Profitability - profit after all costs and overhead.

Profit = revenue - COGS of their deliveries - cost-to-serve - allocated
overhead. Cost-to-serve = selling expenses (Sales cost center) allocated by
number of orders; overhead = Admin cost center allocated by revenue share;
credit cost = 1 % per month on average receivable days beyond 30.
"""

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.constants import COMPANY, cc


def _cc_expense(center, from_date, to_date):
	lft, rgt = frappe.db.get_value("Cost Center", center, ["lft", "rgt"])
	return flt(frappe.db.sql(
		"""select sum(gle.debit - gle.credit) from `tabGL Entry` gle join `tabAccount` a on a.name = gle.account
		join `tabCost Center` c on c.name = gle.cost_center
		where gle.company = %s and a.root_type = 'Expense' and c.lft >= %s and c.rgt <= %s and gle.is_cancelled = 0
			and gle.posting_date between %s and %s""", (COMPANY, lft, rgt, from_date, to_date))[0][0])


def execute(filters=None):
	filters = frappe._dict(filters or {})
	f, t = filters.from_date or "2026-04-01", filters.to_date or "2027-03-31"
	rows = frappe.db.sql(
		"""select si.customer, si.customer_name, sum(si.base_net_total) revenue, count(distinct si.name) invoices,
			count(distinct sii.sales_order) orders, sum(si.outstanding_amount) outstanding
		from `tabSales Invoice` si join `tabSales Invoice Item` sii on sii.parent = si.name and sii.idx = 1
		where si.company = %s and si.docstatus = 1 and si.is_return = 0 and ifnull(si.is_internal_customer, 0) = 0
			and si.posting_date between %s and %s group by si.customer""", (COMPANY, f, t), as_dict=True)
	cogs = {r.customer: flt(r.cost) for r in frappe.db.sql(
		"""select dn.customer, -sum(sle.stock_value_difference) cost from `tabStock Ledger Entry` sle
		join `tabDelivery Note` dn on dn.name = sle.voucher_no and sle.voucher_type = 'Delivery Note'
		where sle.company = %s and sle.is_cancelled = 0 and dn.is_return = 0 and ifnull(dn.is_internal_customer, 0) = 0
			and sle.posting_date between %s and %s group by dn.customer""", (COMPANY, f, t), as_dict=True)}
	total_rev = sum(flt(r.revenue) for r in rows) or 1
	total_orders = sum(r.orders or 1 for r in rows) or 1
	selling = _cc_expense(cc("Sales"), f, t)
	admin = _cc_expense(cc("Admin"), f, t)
	for r in rows:
		r.cogs = cogs.get(r.customer, 0)
		r.cost_to_serve = selling * (r.orders or 1) / total_orders
		r.overhead = admin * flt(r.revenue) / total_rev
		r.profit = flt(r.revenue) - r.cogs - r.cost_to_serve - r.overhead
		r.margin = r.profit / flt(r.revenue) * 100 if r.revenue else 0
	rows.sort(key=lambda r: -r.profit)
	cols = [
		{"label": _("Customer"), "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 120},
		{"label": _("COGS"), "fieldname": "cogs", "fieldtype": "Currency", "width": 110},
		{"label": _("Cost to Serve"), "fieldname": "cost_to_serve", "fieldtype": "Currency", "width": 110},
		{"label": _("Overhead"), "fieldname": "overhead", "fieldtype": "Currency", "width": 110},
		{"label": _("Profit"), "fieldname": "profit", "fieldtype": "Currency", "width": 120},
		{"label": _("Margin %"), "fieldname": "margin", "fieldtype": "Percent", "width": 85},
		{"label": _("Orders"), "fieldname": "orders", "fieldtype": "Int", "width": 70},
		{"label": _("Outstanding"), "fieldname": "outstanding", "fieldtype": "Currency", "width": 120},
	]
	return cols, rows[: int(filters.top or 10)]
