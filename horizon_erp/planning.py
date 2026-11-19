"""Demand history, forecast and reorder-level maths for Horizon.

Demand source
	Item Demand History rows (legacy months imported from the old ERP) plus
	actual ERPNext consumption: customer deliveries and material issued to
	production. Branch transfers and internal moves are not demand.

Forecast for a month M
	base     = average monthly demand of the last 6 months, de-seasonalised
	seasonal = index of M's quarter for items with demand pattern
	           "Seasonal - Q4 Spike" (Q4 = Jan-Mar, Indian fiscal year);
	           1.0 for everything else
	forecast = base x seasonal

Reorder level (assignment formula)
	average daily usage = forecast for the lead-time window / days
	safety stock        = average daily usage x lead time x criticality factor
	                      (A 0.5, B 0.3, C 0.15)
	reorder point       = average daily usage x lead time + safety stock
	reorder qty         = max(30 days of usage, item minimum order qty)
"""

import math

import frappe
from frappe.utils import add_days, add_months, cint, flt, get_first_day, getdate, nowdate

from horizon_erp.constants import COMPANY

CRITICALITY_FACTOR = {"A - Critical": 0.5, "B - Important": 0.3, "C - Standard": 0.15}
Q4_MONTHS = (1, 2, 3)
HISTORY_MONTHS = 6


def month_key(d):
	return getdate(d).strftime("%Y-%m")


def erpnext_monthly_demand(item_codes, from_date, to_date):
	"""{(item, 'YYYY-MM'): qty} from deliveries (non-internal) and production issues."""
	if not item_codes:
		return {}
	rows = frappe.db.sql(
		"""
		select sle.item_code, date_format(sle.posting_date, '%%Y-%%m') ym, -sum(sle.actual_qty) qty
		from `tabStock Ledger Entry` sle
		left join `tabDelivery Note` dn on sle.voucher_type = 'Delivery Note' and dn.name = sle.voucher_no
		left join `tabStock Entry` se on sle.voucher_type = 'Stock Entry' and se.name = sle.voucher_no
		where sle.company = %(company)s and sle.is_cancelled = 0 and sle.actual_qty < 0
			and sle.item_code in %(items)s
			and sle.posting_date between %(from_date)s and %(to_date)s
			and (
				(sle.voucher_type = 'Delivery Note' and ifnull(dn.is_internal_customer, 0) = 0 and ifnull(dn.is_return, 0) = 0)
				or (sle.voucher_type = 'Stock Entry' and se.purpose in ('Manufacture', 'Material Issue', 'Material Consumption for Manufacture'))
				or (sle.voucher_type = 'Sales Invoice')
			)
		group by sle.item_code, ym
		""",
		{"company": COMPANY, "items": tuple(item_codes), "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)
	return {(r.item_code, r.ym): flt(r.qty) for r in rows}


def monthly_demand(item_codes, from_date, to_date):
	"""Merged history: ERPNext actuals, overridden by Item Demand History rows.

	The legacy ERP ran in parallel until cut-over, so for any month where an
	imported legacy figure exists it is the complete number; ERPNext actuals
	fill the months after cut-over.
	"""
	out = erpnext_monthly_demand(item_codes, from_date, to_date)
	for r in frappe.get_all(
		"Item Demand History",
		filters={"item_code": ("in", item_codes or [""]), "period_start": ("between", [get_first_day(from_date), to_date])},
		fields=["item_code", "period", "demand_qty"],
	):
		out[(r.item_code, r.period)] = flt(r.demand_qty)
	return out


def seasonal_index(item_code, history):
	"""Q4 average / non-Q4 average over all history months available."""
	pattern = frappe.get_cached_value("Item", item_code, "hml_demand_pattern")
	if pattern != "Seasonal - Q4 Spike":
		return 1.0
	q4 = [q for (i, ym), q in history.items() if i == item_code and int(ym[5:]) in Q4_MONTHS]
	rest = [q for (i, ym), q in history.items() if i == item_code and int(ym[5:]) not in Q4_MONTHS]
	if not q4 or not rest or not sum(rest):
		return 1.0
	return round((sum(q4) / len(q4)) / (sum(rest) / len(rest)), 2)


def forecast(item_code, month_start, history=None, index=None):
	"""Forecast demand qty for the month starting `month_start`."""
	month_start = get_first_day(month_start)
	if history is None:
		history = monthly_demand([item_code], add_months(month_start, -24), add_days(month_start, -1))
	if index is None:
		index = seasonal_index(item_code, history)
	values = []
	for i in range(1, HISTORY_MONTHS + 1):
		m = add_months(month_start, -i)
		q = history.get((item_code, month_key(m)))
		if q is None:
			continue
		values.append(q / (index if m.month in Q4_MONTHS else 1.0))
	if not values:
		return 0.0
	base = sum(values) / len(values)
	return round(base * (index if month_start.month in Q4_MONTHS else 1.0), 2)


def reorder_parameters(item_code, on_date=None, history=None):
	on_date = getdate(on_date or nowdate())
	item = frappe.get_cached_value(
		"Item", item_code, ["lead_time_days", "hml_criticality", "min_order_qty"], as_dict=True
	)
	lead = max(cint(item.lead_time_days), 1)
	if history is None:
		history = monthly_demand([item_code], add_months(on_date, -24), on_date)
	index = seasonal_index(item_code, history)
	# usage over the coming lead-time window: forecast of the months it covers
	months = sorted({get_first_day(add_days(on_date, d)) for d in range(0, lead + 1, 15)} | {get_first_day(add_days(on_date, lead))})
	monthly = [forecast(item_code, m, history, index) for m in months]
	avg_daily = (sum(monthly) / len(monthly)) / 30 if monthly else 0
	factor = CRITICALITY_FACTOR.get(item.hml_criticality or "C - Standard", 0.15)
	safety = avg_daily * lead * factor
	reorder_point = avg_daily * lead + safety
	reorder_qty = max(avg_daily * 30, flt(item.min_order_qty))
	return frappe._dict(
		avg_daily_usage=round(avg_daily, 3),
		lead_time=lead,
		seasonal_index=index,
		safety_stock=math.ceil(safety),
		reorder_point=math.ceil(reorder_point),
		reorder_qty=math.ceil(reorder_qty),
	)
