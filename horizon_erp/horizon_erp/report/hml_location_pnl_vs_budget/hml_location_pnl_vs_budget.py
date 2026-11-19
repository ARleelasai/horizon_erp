"""HML Location P&L vs Budget - consolidated P&L by location and period.

Columns per location (Branch dimension: HQ Mumbai, DC Delhi) and the
company total, for the selected period. Budget comes from Budgets set
against the Branch dimension (location expense budgets) and is phased by
Monthly Distribution. This is the separate-P&L view Finance asked for,
without splitting the company (decision D-01).
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate, nowdate

from horizon_erp.constants import BRANCH_DELHI, BRANCH_MUMBAI, COMPANY

LINES = [
	("Revenue", "Income", None),
	("Cost of goods sold", "Expense", "Cost of Goods Sold"),
	("Manufacturing wages and power", "Expense", ("Manufacturing Wages", "Contract Labour Charges", "Factory Power and Fuel", "Rework Cost")),
	("Salaries", "Expense", ("Salary",)),
	("Rent and utilities", "Expense", ("Factory Rent", "Warehouse Rent", "Utility Expenses", "Office Rent")),
	("Depreciation", "Expense", ("Depreciation",)),
	("Repairs and maintenance", "Expense", ("Repairs and Maintenance - Plant",)),
	("Other expenses", "Expense", "*"),
]


def _amount(branch, root, accounts, f, exclude=()):
	cond, params = "", {**f, "branch": branch}
	if branch:
		cond += " and gle.branch = %(branch)s"
	if accounts == "Cost of Goods Sold":
		cond += " and acc.account_type = 'Cost of Goods Sold'"
	elif accounts == "*":
		cond += " and acc.account_type != 'Cost of Goods Sold' and acc.account_name not in %(exclude)s"
		params["exclude"] = tuple(exclude) or ("",)
	elif accounts:
		cond += " and acc.account_name in %(accounts)s"
		params["accounts"] = tuple(accounts)
	sign = "gle.credit - gle.debit" if root == "Income" else "gle.debit - gle.credit"
	return flt(frappe.db.sql(
		f"""select sum({sign}) from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where gle.company = %(company)s and gle.is_cancelled = 0 and acc.root_type = %(root)s
			and gle.posting_date between %(from_date)s and %(to_date)s
			and ifnull(gle.voucher_type, '') != 'Period Closing Voucher' {cond}""",
		{**params, "root": root})[0][0])


def _budget(branch, f):
	if not branch:
		branch_cond, params = "", {}
	else:
		branch_cond, params = "and b.budget_against = 'Branch' and b.branch = %(branch)s", {"branch": branch}
	rows = frappe.db.sql(
		f"""select ba.budget_amount, b.monthly_distribution from `tabBudget` b join `tabBudget Account` ba on ba.parent = b.name
		where b.company = %(company)s and b.docstatus = 1 and b.fiscal_year = '2026-2027' {branch_cond}
		{'' if branch else "and b.budget_against = 'Branch'"}""",
		{**f, **params}, as_dict=True)
	from horizon_erp.horizon_erp.report.hml_budget_variance.hml_budget_variance import month_share

	total = 0
	for r in rows:
		m = getdate(f["from_date"])
		while m <= getdate(f["to_date"]):
			total += flt(r.budget_amount) * month_share(r.monthly_distribution, m) / 100
			m = add_months(m, 1)
	return total


def execute(filters=None):
	filters = frappe._dict(filters or {})
	f = {"company": COMPANY, "from_date": filters.from_date or "2026-04-01", "to_date": filters.to_date or nowdate()}
	locations = [(BRANCH_MUMBAI, "mum"), (BRANCH_DELHI, "del"), (None, "tot")]
	named = [a for _l, _r, accs in LINES if isinstance(accs, tuple) for a in accs]
	data, totals = [], {k: {"income": 0, "expense": 0} for _b, k in locations}
	for label, root, accounts in LINES:
		row = {"line": label}
		for branch, key in locations:
			v = _amount(branch, root, accounts, f, exclude=named)
			row[key] = v
			totals[key]["income" if root == "Income" else "expense"] += v
		data.append(row)
	net = {"line": _("Net profit"), "bold": 1}
	margin = {"line": _("Net margin %")}
	for _b, key in locations:
		net[key] = totals[key]["income"] - totals[key]["expense"]
		margin[key] = net[key] / totals[key]["income"] * 100 if totals[key]["income"] else 0
	data += [net, margin]
	budget = {"line": _("Location expense budget (period)")}
	actual_exp = {"line": _("Location expenses actual (period)")}
	for branch, key in locations:
		budget[key] = _budget(branch, f)
		actual_exp[key] = totals[key]["expense"] - (data[1][key])  # excluding COGS
	var = {"line": _("Expense variance vs budget"), "bold": 1}
	for _b, key in locations:
		var[key] = actual_exp[key] - budget[key]
	data += [{}, budget, actual_exp, var]
	cols = [
		{"label": _("Line"), "fieldname": "line", "fieldtype": "Data", "width": 260},
		{"label": _("HQ Mumbai"), "fieldname": "mum", "fieldtype": "Currency", "width": 150},
		{"label": _("DC Delhi"), "fieldname": "del", "fieldtype": "Currency", "width": 150},
		{"label": _("Company Total"), "fieldname": "tot", "fieldtype": "Currency", "width": 160},
	]
	return cols, data
