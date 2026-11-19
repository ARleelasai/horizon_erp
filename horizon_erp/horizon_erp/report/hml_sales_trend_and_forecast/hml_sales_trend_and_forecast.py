"""HML Sales Trend and Forecast - revenue by quarter with a 2-quarter forecast.

History = invoiced revenue (ERPNext) plus legacy quarters valued at current
list price from Item Demand History (legacy ERP, before cut-over). Forecast =
least-squares trend on de-seasonalised quarters x Q4 seasonal index (Indian
fiscal Q4 = Jan-Mar).
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from horizon_erp.constants import COMPANY


def fy_quarter(d):
	d = getdate(d)
	fy = d.year if d.month >= 4 else d.year - 1
	q = ((d.month - 4) % 12) // 3 + 1
	return f"FY{str(fy)[2:]}-{str(fy + 1)[2:]} Q{q}", (fy, q)


def execute(filters=None):
	quarters = {}
	prices = dict(frappe.db.sql("select item_code, price_list_rate from `tabItem Price` where price_list = 'HML Standard Selling'"))
	for r in frappe.get_all("Item Demand History", filters={"source": "Legacy ERP"}, fields=["item_code", "period_start", "demand_qty"]):
		if r.item_code in prices:
			label, key = fy_quarter(r.period_start)
			q = quarters.setdefault(key, {"quarter": label, "legacy": 0, "erpnext": 0})
			q["legacy"] += flt(r.demand_qty) * flt(prices[r.item_code])
	for r in frappe.db.sql(
		"""select posting_date, base_net_total from `tabSales Invoice` where company = %s and docstatus = 1 and is_return = 0
		and ifnull(is_internal_customer, 0) = 0""", COMPANY, as_dict=True):
		label, key = fy_quarter(r.posting_date)
		q = quarters.setdefault(key, {"quarter": label, "legacy": 0, "erpnext": 0})
		q["erpnext"] += flt(r.base_net_total)
	keys = sorted(quarters)
	for k in keys:
		q = quarters[k]
		# a quarter covered by both sources during the parallel run counts the legacy figure (complete)
		q["revenue"] = q["legacy"] if q["legacy"] else q["erpnext"]
	q4 = [quarters[k]["revenue"] for k in keys if k[1] == 4]
	rest = [quarters[k]["revenue"] for k in keys if k[1] != 4]
	index = (sum(q4) / len(q4)) / (sum(rest) / len(rest)) if q4 and rest and sum(rest) else 1
	ys = [quarters[k]["revenue"] / (index if k[1] == 4 else 1) for k in keys]
	n = len(ys)
	xs = list(range(n))
	if n >= 2:
		mx, my = sum(xs) / n, sum(ys) / n
		slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sum((x - mx) ** 2 for x in xs) or 1)
		intercept = my - slope * mx
	else:
		slope, intercept = 0, (ys[0] if ys else 0)
	data = [{"quarter": quarters[k]["quarter"], "revenue": quarters[k]["revenue"], "source": "Legacy ERP" if quarters[k]["legacy"] else "ERPNext"} for k in keys]
	last = keys[-1] if keys else (2026, 3)
	fy, q = last
	for i in range(1, 3):
		q += 1
		if q > 4:
			fy, q = fy + 1, 1
		value = (intercept + slope * (n - 1 + i)) * (index if q == 4 else 1)
		data.append({"quarter": f"FY{str(fy)[2:]}-{str(fy + 1)[2:]} Q{q}", "forecast": max(value, 0), "source": "Forecast"})
	cols = [
		{"label": _("Quarter"), "fieldname": "quarter", "fieldtype": "Data", "width": 130},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 140},
		{"label": _("Forecast"), "fieldname": "forecast", "fieldtype": "Currency", "width": 140},
		{"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 110},
	]
	chart = {
		"data": {"labels": [d["quarter"] for d in data],
			"datasets": [{"name": _("Revenue"), "values": [flt(d.get("revenue")) for d in data]},
				{"name": _("Forecast"), "values": [flt(d.get("forecast")) for d in data]}]},
		"type": "bar",
	}
	return cols, data, None, chart, [{"label": _("Q4 seasonal index"), "value": round(index, 2), "indicator": "Blue"}]
