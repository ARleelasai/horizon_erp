"""Budget helpers: position per cost center / account, alerts.

budget_position() returns annual budget, actual booked (GL) + committed
(open POs) and this document's amount - used by Budget Overage Approval and
the budget reports. alert_cost_centers_over_90() is a daily job.
"""

import frappe
from frappe.utils import flt, getdate, nowdate

from horizon_erp.constants import COMPANY
from horizon_erp.notify import notify


def budget_rows(company=COMPANY, fiscal_year=None):
	fiscal_year = fiscal_year or frappe.defaults.get_user_default("fiscal_year") or "2026-2027"
	return frappe.db.sql(
		"""select b.name budget, b.cost_center, ba.account, ba.budget_amount, b.monthly_distribution
		from `tabBudget` b join `tabBudget Account` ba on ba.parent = b.name
		where b.company = %s and b.fiscal_year = %s and b.docstatus = 1 and b.budget_against = 'Cost Center'""",
		(company, fiscal_year),
		as_dict=True,
	)


def actual(company, cost_center, account, from_date, to_date):
	lft, rgt = frappe.db.get_value("Cost Center", cost_center, ["lft", "rgt"])
	return flt(
		frappe.db.sql(
			"""select sum(gle.debit - gle.credit) from `tabGL Entry` gle
			join `tabCost Center` cc on cc.name = gle.cost_center
			where gle.company = %s and gle.account = %s and gle.is_cancelled = 0
				and cc.lft >= %s and cc.rgt <= %s and gle.posting_date between %s and %s""",
			(company, account, lft, rgt, from_date, to_date),
		)[0][0]
	)


def budget_position(company, cost_center, account, doc=None, fiscal_year="2026-2027"):
	fy = frappe.get_cached_doc("Fiscal Year", fiscal_year)
	budget = flt(
		frappe.db.sql(
			"""select sum(ba.budget_amount) from `tabBudget` b join `tabBudget Account` ba on ba.parent = b.name
			where b.company = %s and b.cost_center = %s and ba.account = %s and b.fiscal_year = %s and b.docstatus = 1""",
			(company, cost_center, account, fiscal_year),
		)[0][0]
	)
	booked = actual(company, cost_center, account, fy.year_start_date, fy.year_end_date)
	this_doc = 0
	if doc is not None:
		if doc.doctype == "Journal Entry":
			this_doc = sum(flt(r.debit) - flt(r.credit) for r in doc.accounts if r.account == account and r.cost_center == cost_center)
		else:
			this_doc = sum(flt(r.base_net_amount) for r in doc.items if r.get("expense_account") == account and r.cost_center == cost_center)
	return frappe._dict(budget=budget, actual=booked, this_document=this_doc)


def alert_cost_centers_over_90():
	"""Daily: notify the cost-center owner when spend passes 90 % of the annual budget."""
	fy = frappe.get_cached_doc("Fiscal Year", "2026-2027")
	for row in budget_rows():
		spent = actual(COMPANY, row.cost_center, row.account, fy.year_start_date, nowdate())
		if not flt(row.budget_amount) or spent / flt(row.budget_amount) < 0.9:
			continue
		owner = frappe.db.get_value("Cost Center", row.cost_center, "hml_owner")
		pct = spent / flt(row.budget_amount) * 100
		key = f"hml_budget_alert::{row.budget}::{row.account}"
		if frappe.cache.get_value(key):
			continue
		frappe.cache.set_value(key, 1, expires_in_sec=7 * 86400)
		notify(
			[owner] if owner else [],
			subject=f"Budget alert: {row.cost_center} / {row.account} at {pct:.0f} %",
			message=f"<p>Spend Rs {spent:,.0f} against an annual budget of Rs {row.budget_amount:,.0f} ({pct:.0f} %).</p>",
			reference_doctype="Budget",
			reference_name=row.budget,
		)
