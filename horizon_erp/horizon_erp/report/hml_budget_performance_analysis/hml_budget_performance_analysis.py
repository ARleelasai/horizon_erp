"""HML Budget Performance Analysis - what drives the variance.

For each cost center / account with a YTD variance, its share of the total
variance and the largest transactions behind the actual spend (top 3
vouchers), so a manager can see *why* - e.g. one breakdown repair, a price
increase, or a one-off - rather than just the number.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from horizon_erp.constants import COMPANY
from horizon_erp.horizon_erp.report.hml_budget_variance.hml_budget_variance import execute as variance


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_cols, rows, *_ = variance(filters)
	total = sum(abs(r["ytd_actual"] - r["ytd_budget"]) for r in rows) or 1
	upto = getdate(filters.upto or nowdate())
	data = []
	for r in sorted(rows, key=lambda r: -abs(r["ytd_actual"] - r["ytd_budget"])):
		var = r["ytd_actual"] - r["ytd_budget"]
		lft, rgt = frappe.db.get_value("Cost Center", r["cost_center"], ["lft", "rgt"])
		top = frappe.db.sql(
			"""select gle.voucher_type, gle.voucher_no, sum(gle.debit - gle.credit) amt, max(gle.remarks) remarks
			from `tabGL Entry` gle join `tabCost Center` cc on cc.name = gle.cost_center
			where gle.company = %s and gle.account = %s and cc.lft >= %s and cc.rgt <= %s and gle.is_cancelled = 0
				and gle.posting_date between '2026-04-01' and %s
			group by gle.voucher_no order by amt desc limit 3""",
			(COMPANY, r["account"], lft, rgt, upto),
			as_dict=True,
		)
		data.append(
			{
				"cost_center": r["cost_center"], "account": r["account"], "ytd_budget": r["ytd_budget"], "ytd_actual": r["ytd_actual"],
				"variance": var, "share": abs(var) / total * 100, "direction": "Over" if var > 0 else "Saving",
				"drivers": "; ".join(f"{t.voucher_no} Rs {flt(t.amt):,.0f} ({(t.remarks or '')[:50]})" for t in top),
			}
		)
	cols = [
		{"label": _("Cost Center"), "fieldname": "cost_center", "fieldtype": "Data", "width": 150},
		{"label": _("Account"), "fieldname": "account", "fieldtype": "Data", "width": 190},
		{"label": _("YTD Budget"), "fieldname": "ytd_budget", "fieldtype": "Currency", "width": 115},
		{"label": _("YTD Actual"), "fieldname": "ytd_actual", "fieldtype": "Currency", "width": 115},
		{"label": _("Variance"), "fieldname": "variance", "fieldtype": "Currency", "width": 115},
		{"label": _("Share of Total Variance %"), "fieldname": "share", "fieldtype": "Percent", "width": 120},
		{"label": _("Over / Saving"), "fieldname": "direction", "fieldtype": "Data", "width": 90},
		{"label": _("Largest Transactions (drivers)"), "fieldname": "drivers", "fieldtype": "Data", "width": 520},
	]
	return cols, data
