"""HML Budget Variance - monthly, YTD and full-year, with run-rate forecast.

Budget for a period = annual budget x Monthly Distribution % of its months
(Q4-weighted distribution for manufacturing). Flags: YTD over budget by more
than 10 % (red); annual budget more than 90 % consumed (alert). Year-end
forecast = YTD actual / months elapsed x 12 (straight run-rate).
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, month_diff, nowdate

from horizon_erp.accounts.budget import actual, budget_rows
from horizon_erp.constants import COMPANY


def month_share(distribution, month_date):
	if not distribution:
		return 100 / 12
	d = frappe.get_cached_doc("Monthly Distribution", distribution)
	return next((flt(p.percentage_allocation) for p in d.percentages if p.month == month_date.strftime("%B")), 100 / 12)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	fy = frappe.get_cached_doc("Fiscal Year", filters.fiscal_year or "2026-2027")
	upto = min(getdate(filters.upto or nowdate()), getdate(fy.year_end_date))
	month_start, month_end = get_first_day(upto), get_last_day(upto)
	months_elapsed = month_diff(upto, fy.year_start_date)
	data = []
	for b in budget_rows(COMPANY, fy.name):
		if filters.cost_center and b.cost_center != filters.cost_center:
			continue
		annual = flt(b.budget_amount)
		ytd_budget = 0
		m = getdate(fy.year_start_date)
		while m <= month_end:
			ytd_budget += annual * month_share(b.monthly_distribution, m) / 100
			m = add_months(m, 1)
		mon_budget = annual * month_share(b.monthly_distribution, month_start) / 100
		mon_actual = actual(COMPANY, b.cost_center, b.account, month_start, month_end)
		ytd_actual = actual(COMPANY, b.cost_center, b.account, fy.year_start_date, upto)
		forecast = ytd_actual / months_elapsed * 12 if months_elapsed else ytd_actual
		var_pct = (ytd_actual - ytd_budget) / ytd_budget * 100 if ytd_budget else 0
		data.append(
			{
				"cost_center": b.cost_center, "account": b.account, "annual": annual,
				"month_budget": mon_budget, "month_actual": mon_actual,
				"month_var_pct": (mon_actual - mon_budget) / mon_budget * 100 if mon_budget else 0,
				"ytd_budget": ytd_budget, "ytd_actual": ytd_actual, "ytd_var_pct": var_pct,
				"used_pct": ytd_actual / annual * 100 if annual else 0,
				"forecast": forecast, "forecast_var": forecast - annual,
				"over_10": 1 if var_pct > 10 else 0, "alert_90": 1 if annual and ytd_actual / annual >= 0.9 else 0,
			}
		)
	cols = [
		{"label": _("Cost Center"), "fieldname": "cost_center", "fieldtype": "Data", "width": 160},
		{"label": _("Account"), "fieldname": "account", "fieldtype": "Data", "width": 200},
		{"label": _("Annual Budget"), "fieldname": "annual", "fieldtype": "Currency", "width": 120},
		{"label": _("Month Budget"), "fieldname": "month_budget", "fieldtype": "Currency", "width": 115},
		{"label": _("Month Actual"), "fieldname": "month_actual", "fieldtype": "Currency", "width": 115},
		{"label": _("Month Var %"), "fieldname": "month_var_pct", "fieldtype": "Percent", "width": 95},
		{"label": _("YTD Budget"), "fieldname": "ytd_budget", "fieldtype": "Currency", "width": 115},
		{"label": _("YTD Actual"), "fieldname": "ytd_actual", "fieldtype": "Currency", "width": 115},
		{"label": _("YTD Var %"), "fieldname": "ytd_var_pct", "fieldtype": "Percent", "width": 90},
		{"label": _("Annual Used %"), "fieldname": "used_pct", "fieldtype": "Percent", "width": 100},
		{"label": _("Year-end Forecast"), "fieldname": "forecast", "fieldtype": "Currency", "width": 125},
		{"label": _("Forecast vs Budget"), "fieldname": "forecast_var", "fieldtype": "Currency", "width": 125},
		{"label": _("> 10 % over"), "fieldname": "over_10", "fieldtype": "Check", "width": 80},
		{"label": _(">= 90 % used"), "fieldname": "alert_90", "fieldtype": "Check", "width": 85},
	]
	by_cc = {}
	for d in data:
		x = by_cc.setdefault(d["cost_center"], [0, 0])
		x[0] += d["ytd_budget"]
		x[1] += d["ytd_actual"]
	chart = {
		"data": {"labels": list(by_cc), "datasets": [{"name": _("YTD Budget"), "values": [v[0] for v in by_cc.values()]},
			{"name": _("YTD Actual"), "values": [v[1] for v in by_cc.values()]}]},
		"type": "bar",
	}
	summary = [
		{"label": _("Lines > 10 % over (YTD)"), "value": sum(d["over_10"] for d in data), "indicator": "Red"},
		{"label": _("Lines >= 90 % of annual"), "value": sum(d["alert_90"] for d in data), "indicator": "Orange"},
		{"label": _("Forecast overspend"), "value": sum(max(d["forecast_var"], 0) for d in data), "datatype": "Currency", "indicator": "Red"},
	]
	return cols, data, None, chart, summary
