"""HML Demand Forecast vs Actual.

For each item and month: the forecast that would have been made at the start
of that month (using only earlier history, horizon_erp.planning.forecast) vs
the actual demand recorded for the month. Shows forecast error and the Q4
seasonal index used for spares.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, getdate

from horizon_erp.planning import Q4_MONTHS, forecast, month_key, monthly_demand, seasonal_index


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start = get_first_day(filters.from_month or "2025-10-01")
	end = get_first_day(filters.to_month or "2026-10-01")
	item_filters = {"disabled": 0, "is_stock_item": 1}
	if filters.item_group:
		item_filters["item_group"] = filters.item_group
	if filters.item_code:
		item_filters["name"] = filters.item_code
	items = frappe.get_all("Item", filters=item_filters, pluck="name")
	history = monthly_demand(items, add_months(start, -30), add_months(end, 1))
	months = []
	m = start
	while m <= end:
		months.append(m)
		m = add_months(m, 1)

	data = []
	for item in items:
		if not any((item, month_key(mm)) in history for mm in months):
			continue
		index = seasonal_index(item, history)
		abs_err = actual_total = 0
		for mm in months:
			prior = {k: v for k, v in history.items() if k[0] == item and k[1] < month_key(mm)}
			fc = forecast(item, mm, prior, index)
			actual = flt(history.get((item, month_key(mm))))
			abs_err += abs(actual - fc)
			actual_total += actual
			if filters.summary_only:
				continue
			data.append(
				{
					"item_code": item,
					"month": mm.strftime("%b %Y"),
					"q4": 1 if mm.month in Q4_MONTHS else 0,
					"seasonal_index": index,
					"forecast": fc,
					"actual": actual,
					"variance": actual - fc,
					"variance_pct": (actual - fc) / fc * 100 if fc else None,
				}
			)
		if filters.summary_only:
			data.append(
				{
					"item_code": item,
					"month": f"{start.strftime('%b %Y')} - {end.strftime('%b %Y')}",
					"seasonal_index": index,
					"actual": actual_total,
					"mape": abs_err / actual_total * 100 if actual_total else None,
				}
			)
	columns = [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 160},
		{"label": _("Q4"), "fieldname": "q4", "fieldtype": "Check", "width": 50},
		{"label": _("Seasonal Index"), "fieldname": "seasonal_index", "fieldtype": "Float", "precision": 2, "width": 110},
		{"label": _("Forecast"), "fieldname": "forecast", "fieldtype": "Float", "precision": 1, "width": 100},
		{"label": _("Actual"), "fieldname": "actual", "fieldtype": "Float", "precision": 1, "width": 100},
		{"label": _("Variance"), "fieldname": "variance", "fieldtype": "Float", "precision": 1, "width": 100},
		{"label": _("Variance %"), "fieldname": "variance_pct", "fieldtype": "Percent", "width": 100},
	]
	if filters.summary_only:
		columns.append({"label": _("Forecast Error (WAPE %)"), "fieldname": "mape", "fieldtype": "Percent", "width": 150})
	chart = None
	if filters.item_code and not filters.summary_only:
		chart = {
			"data": {
				"labels": [d["month"] for d in data],
				"datasets": [{"name": _("Forecast"), "values": [d["forecast"] for d in data]}, {"name": _("Actual"), "values": [d["actual"] for d in data]}],
			},
			"type": "line",
		}
	return columns, data, None, chart
