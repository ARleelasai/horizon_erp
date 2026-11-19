"""Cost Center Wise P&L - monthly and YTD by department / product category.

Rows: each cost center (tree, group rows roll up their children) with
Income, Expense and Net Profit lines. Columns: one per month of the fiscal
year up to `to_date`, then YTD and Net Margin %.

Optional Branch (Location) filter turns this into a per-location P&L, which is
how HQ Mumbai and DC Delhi profitability is reported without separate
companies (decision D-01).
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, getdate

from horizon_erp.constants import COMPANY


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.company or COMPANY
	fy = frappe.get_cached_doc("Fiscal Year", filters.fiscal_year)
	from_date = getdate(fy.year_start_date)
	to_date = getdate(filters.to_date) if filters.to_date else getdate(fy.year_end_date)
	to_date = min(to_date, getdate(fy.year_end_date))

	months = []
	d = get_first_day(from_date)
	while d <= to_date:
		months.append(d)
		d = add_months(d, 1)

	columns = get_columns(months)
	amounts = get_amounts(filters, from_date, to_date)
	data = build_rows(filters, months, amounts)
	chart = get_chart(data, months)
	return columns, data, None, chart


def get_amounts(filters, from_date, to_date):
	"""{(cost_center, root_type, 'YYYY-MM'): amount} with income positive, expense positive."""
	branch_cond = "and gle.branch = %(branch)s" if filters.branch else ""
	rows = frappe.db.sql(
		f"""
		select gle.cost_center, acc.root_type,
			date_format(gle.posting_date, '%%Y-%%m') as ym,
			sum(gle.debit - gle.credit) as amount
		from `tabGL Entry` gle
		join `tabAccount` acc on acc.name = gle.account
		where gle.company = %(company)s
			and gle.is_cancelled = 0
			and gle.posting_date between %(from_date)s and %(to_date)s
			and acc.root_type in ('Income', 'Expense')
			and ifnull(gle.voucher_type, '') != 'Period Closing Voucher'
			{branch_cond}
		group by gle.cost_center, acc.root_type, ym
		""",
		{**filters, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)
	out = {}
	for r in rows:
		amount = -flt(r.amount) if r.root_type == "Income" else flt(r.amount)
		out[(r.cost_center or _("Not Set"), r.root_type, r.ym)] = amount
	return out


def build_rows(filters, months, amounts):
	centers = frappe.get_all(
		"Cost Center",
		filters={"company": filters.company},
		fields=["name", "parent_cost_center", "is_group", "lft", "rgt"],
		order_by="lft",
	)
	if not centers:
		return []
	root_lft = min(c.lft for c in centers)
	depth = {}
	for c in centers:
		depth[c.name] = 0 if c.lft == root_lft else depth.get(c.parent_cost_center, 0) + 1

	keys = [m.strftime("%Y-%m") for m in months]

	def total(center, root_type, ym):
		# group rows roll up all descendants
		return sum(
			amounts.get((c.name, root_type, ym), 0)
			for c in centers
			if c.lft >= center.lft and c.rgt <= center.rgt
		)

	data = []
	for c in centers:
		if c.lft == root_lft:
			continue  # company root = whole P&L; shown as the total row
		data.extend(_center_rows(c, depth[c.name] - 1, keys, total))
	root = next(c for c in centers if c.lft == root_lft)
	data.extend(_center_rows(root, 0, keys, total, label=_("Total - {0}").format(filters.company)))
	return data


def _center_rows(center, indent, keys, total, label=None):
	income = {k: total(center, "Income", k) for k in keys}
	expense = {k: total(center, "Expense", k) for k in keys}
	if not any(income.values()) and not any(expense.values()):
		return []
	net = {k: income[k] - expense[k] for k in keys}

	def row(line, values, ind, bold=False):
		r = {
			"cost_center": label or center.name,
			"line": line,
			"indent": ind,
			"bold": 1 if bold else 0,
			"is_group": center.is_group,
		}
		for k in keys:
			r[k] = values[k]
		r["ytd"] = sum(values.values())
		return r

	net_row = row(_("Net Profit"), net, indent, bold=True)
	ytd_income = sum(income.values())
	net_row["margin"] = (net_row["ytd"] / ytd_income * 100) if ytd_income else None
	return [
		net_row,
		row(_("Income"), income, indent + 1),
		row(_("Expense"), expense, indent + 1),
	]


def get_columns(months):
	cols = [
		{"label": _("Cost Center"), "fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center", "width": 220},
		{"label": _("Line"), "fieldname": "line", "fieldtype": "Data", "width": 100},
	]
	for m in months:
		cols.append(
			{"label": m.strftime("%b %Y"), "fieldname": m.strftime("%Y-%m"), "fieldtype": "Currency", "width": 115}
		)
	cols += [
		{"label": _("YTD"), "fieldname": "ytd", "fieldtype": "Currency", "width": 130},
		{"label": _("Net Margin %"), "fieldname": "margin", "fieldtype": "Percent", "width": 105},
	]
	return cols


def get_chart(data, months):
	nets = [r for r in data if r["line"] == _("Net Profit") and r["indent"] <= 1 and not r["cost_center"].startswith(_("Total"))]
	if not nets:
		return None
	return {
		"data": {
			"labels": [m.strftime("%b") for m in months],
			"datasets": [
				{"name": r["cost_center"], "values": [r[m.strftime("%Y-%m")] for m in months]} for r in nets[:6]
			],
		},
		"type": "line",
	}
