"""E-mail reports for the scheduler (daily 18:00, monthly 1st 09:00)."""

import frappe
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, nowdate
from frappe.utils.pdf import get_pdf

from horizon_erp.constants import COMPANY, ROLE_FD
from horizon_erp.notify import notify


def _users_with_role(role):
	return [u for u in frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
		if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")]


def daily_summary_data(day=None):
	day = getdate(day or nowdate())
	so = frappe.db.sql(
		"select count(*), ifnull(sum(base_net_total), 0) from `tabSales Order` where company = %s and docstatus = 1 and transaction_date = %s",
		(COMPANY, day),
	)[0]
	wo = frappe.db.sql(
		"""select count(*), ifnull(sum(produced_qty), 0), ifnull(sum(case when hml_has_rework = 1 then 1 else 0 end), 0)
		from `tabWork Order` where company = %s and docstatus = 1 and status = 'Completed' and date(actual_end_date) = %s""",
		(COMPANY, day),
	)[0]
	inv = frappe.db.sql(
		"select count(*), ifnull(sum(base_net_total), 0) from `tabSales Invoice` where company = %s and docstatus = 1 and posting_date = %s and is_return = 0",
		(COMPANY, day),
	)[0]
	open_wo = frappe.db.count("Work Order", {"company": COMPANY, "docstatus": 1, "status": ("in", ["Not Started", "In Process"])})
	pending_po = frappe.db.count("Purchase Order", {"company": COMPANY, "docstatus": 0, "workflow_state": ("like", "Pending%")})
	return frappe._dict(
		day=day, so_count=so[0], so_value=flt(so[1]), wo_completed=wo[0], units=flt(wo[1]), wo_rework=wo[2],
		fpy=((wo[0] - wo[2]) / wo[0] * 100) if wo[0] else None, invoices=inv[0], invoiced=flt(inv[1]),
		open_wo=open_wo, pending_po=pending_po,
	)


def render_daily(d):
	fpy = f"{d.fpy:.0f} %" if d.fpy is not None else "-"
	return f"""
	<h3>Horizon daily summary - {frappe.format(d.day, 'Date')}</h3>
	<table border="1" cellpadding="6" style="border-collapse:collapse;font-family:sans-serif">
	<tr><th align="left">Sales Orders booked</th><td>{d.so_count}</td><td>Rs {d.so_value:,.0f}</td></tr>
	<tr><th align="left">Invoiced</th><td>{d.invoices}</td><td>Rs {d.invoiced:,.0f}</td></tr>
	<tr><th align="left">Work Orders completed</th><td>{d.wo_completed}</td><td>{d.units:g} units, first-pass yield {fpy}</td></tr>
	<tr><th align="left">Work Orders open</th><td colspan="2">{d.open_wo}</td></tr>
	<tr><th align="left">POs waiting for approval</th><td colspan="2">{d.pending_po}</td></tr>
	</table>"""


def send_daily_summary(day=None):
	d = daily_summary_data(day)
	html = render_daily(d)
	pdf = get_pdf(f"<html><body>{html}</body></html>")
	notify(
		_users_with_role(ROLE_FD),
		subject=f"Horizon daily summary {d.day}",
		message=html,
		attachments=[{"fname": f"horizon-daily-{d.day}.pdf", "fcontent": pdf}],
	)
	return {"summary": {k: v for k, v in d.items() if k != "day"}, "findings": []}


def send_monthly_budget_reports(month_start=None):
	"""1st of month: last month's budget vs actual per cost center, to its owner."""
	from horizon_erp.accounts.budget import actual, budget_rows

	month_start = get_first_day(add_months(getdate(month_start or nowdate()), -1))
	month_end = get_last_day(month_start)
	fy_start = getdate("2026-04-01")
	sent, overages = [], []
	by_cc = {}
	for row in budget_rows():
		dist = frappe.get_cached_doc("Monthly Distribution", row.monthly_distribution) if row.monthly_distribution else None
		pct = 100 / 12
		if dist:
			pct = next((flt(p.percentage_allocation) for p in dist.percentages if p.month == month_start.strftime("%B")), pct)
		month_budget = flt(row.budget_amount) * pct / 100
		month_actual = actual(COMPANY, row.cost_center, row.account, month_start, month_end)
		ytd_actual = actual(COMPANY, row.cost_center, row.account, fy_start, month_end)
		var = (month_actual - month_budget) / month_budget * 100 if month_budget else 0
		line = dict(account=row.account, budget=month_budget, actual=month_actual, variance=var, ytd=ytd_actual, annual=flt(row.budget_amount))
		by_cc.setdefault(row.cost_center, []).append(line)
		if var > 10:
			overages.append({"cost_center": row.cost_center, **line})
	for cc, lines in by_cc.items():
		owner = frappe.db.get_value("Cost Center", cc, "hml_owner")
		rows = "".join(
			f"<tr><td>{l['account']}</td><td align='right'>{l['budget']:,.0f}</td><td align='right'>{l['actual']:,.0f}</td>"
			f"<td align='right' style='color:{'#c00' if l['variance'] > 10 else ('#080' if l['variance'] < 0 else '#000')}'>{l['variance']:+.1f} %</td>"
			f"<td align='right'>{l['ytd']:,.0f} / {l['annual']:,.0f}</td></tr>"
			for l in lines
		)
		html = (
			f"<h3>{cc} - budget performance {month_start.strftime('%B %Y')}</h3>"
			"<table border='1' cellpadding='5' style='border-collapse:collapse'>"
			"<tr><th>Account</th><th>Budget</th><th>Actual</th><th>Variance</th><th>YTD / Annual</th></tr>"
			f"{rows}</table><p>Red = over budget by more than 10 %; green = saving. Details: report 'HML Budget Variance'.</p>"
		)
		notify([owner] if owner else _users_with_role(ROLE_FD), subject=f"Budget performance {month_start.strftime('%b %Y')}: {cc}", message=html)
		sent.append(cc)
	return {"sent_to_cost_centers": sent, "findings": overages}
