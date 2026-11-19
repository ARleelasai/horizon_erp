"""HML Supplier Quality Scorecard.

Per supplier, over the selected period:
	Defect rate     = rejected qty / received qty at incoming inspection
	On-time         = receipt lines posted on or before the PO line schedule date
	Price trend     = avg receipt rate in the last 90 days vs the 90 days before,
	                  value-weighted across items (positive = getting dearer)
	Score (0-100)   = 50 % quality + 30 % delivery + 20 % price
	                  quality  = 100 - 10 x defect rate %   (5 % defects -> 50)
	                  delivery = on-time %
	                  price    = 100 - 5 x price increase % (decreases score 100)
	Grade           = A >= 85, B >= 70, else C  (C suppliers go to review)
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from horizon_erp.constants import COMPANY


def execute(filters=None):
	filters = frappe._dict(filters or {})
	to_date = getdate(filters.to_date or nowdate())
	from_date = getdate(filters.from_date or "2026-04-01")
	lines = frappe.db.sql(
		"""
		select pr.supplier, s.supplier_name, s.hml_is_blacklisted as blacklisted, pr.posting_date,
			pri.item_code, pri.received_qty, pri.rejected_qty, pri.base_rate as rate,
			poi.schedule_date
		from `tabPurchase Receipt` pr
		join `tabPurchase Receipt Item` pri on pri.parent = pr.name
		join `tabSupplier` s on s.name = pr.supplier
		left join `tabPurchase Order Item` poi on poi.name = pri.purchase_order_item
		where pr.docstatus = 1 and pr.is_return = 0 and pr.company = %s and ifnull(pr.is_internal_supplier, 0) = 0
			and pr.posting_date between %s and %s
		""",
		(COMPANY, add_days(to_date, -365) if from_date > add_days(to_date, -180) else from_date, to_date),
		as_dict=True,
	)
	recent_from = add_days(to_date, -90)
	prior_from = add_days(to_date, -180)
	sup = {}
	for l in lines:
		s = sup.setdefault(
			l.supplier,
			{"supplier": l.supplier, "supplier_name": l.supplier_name, "blacklisted": l.blacklisted, "receipts": 0, "received": 0,
				"rejected": 0, "on_time": 0, "with_schedule": 0, "recent": {}, "prior": {}},
		)
		if getdate(l.posting_date) >= from_date:
			s["receipts"] += 1
			s["received"] += flt(l.received_qty)
			s["rejected"] += flt(l.rejected_qty)
			if l.schedule_date:
				s["with_schedule"] += 1
				if getdate(l.posting_date) <= getdate(l.schedule_date):
					s["on_time"] += 1
		bucket = "recent" if getdate(l.posting_date) >= recent_from else ("prior" if getdate(l.posting_date) >= prior_from else None)
		if bucket:
			agg = s[bucket].setdefault(l.item_code, [0, 0])
			agg[0] += flt(l.rate) * flt(l.received_qty)
			agg[1] += flt(l.received_qty)
	data = []
	for s in sup.values():
		if not s["receipts"]:
			continue
		defect = s["rejected"] / s["received"] * 100 if s["received"] else 0
		on_time = s["on_time"] / s["with_schedule"] * 100 if s["with_schedule"] else 100
		price = _price_trend(s["recent"], s["prior"])
		score = 0.5 * max(100 - 10 * defect, 0) + 0.3 * on_time + 0.2 * max(min(100 - 5 * (price or 0), 100), 0)
		data.append(
			{
				"supplier": s["supplier"],
				"supplier_name": s["supplier_name"],
				"receipts": s["receipts"],
				"received_qty": s["received"],
				"rejected_qty": s["rejected"],
				"defect_rate": round(defect, 2),
				"on_time_pct": round(on_time, 1),
				"price_trend_pct": price,
				"score": round(score, 1),
				"grade": "A" if score >= 85 else ("B" if score >= 70 else "C"),
				"blacklisted": s["blacklisted"],
			}
		)
	data.sort(key=lambda d: d["score"])
	columns = [
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 140},
		{"label": _("Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 190},
		{"label": _("Receipt Lines"), "fieldname": "receipts", "fieldtype": "Int", "width": 100},
		{"label": _("Received Qty"), "fieldname": "received_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Rejected Qty"), "fieldname": "rejected_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Defect Rate %"), "fieldname": "defect_rate", "fieldtype": "Percent", "width": 110},
		{"label": _("On-time %"), "fieldname": "on_time_pct", "fieldtype": "Percent", "width": 100},
		{"label": _("Price Trend % (90 d)"), "fieldname": "price_trend_pct", "fieldtype": "Percent", "width": 140},
		{"label": _("Score"), "fieldname": "score", "fieldtype": "Float", "precision": 1, "width": 80},
		{"label": _("Grade"), "fieldname": "grade", "fieldtype": "Data", "width": 70},
		{"label": _("Blacklisted"), "fieldname": "blacklisted", "fieldtype": "Check", "width": 90},
	]
	chart = {
		"data": {"labels": [d["supplier_name"] for d in data], "datasets": [{"name": _("Score"), "values": [d["score"] for d in data]}]},
		"type": "bar",
	}
	return columns, data, None, chart


def _price_trend(recent, prior):
	"""Value-weighted % change of average rate for items bought in both windows."""
	change = weight = 0
	for item, (val, qty) in recent.items():
		if item in prior and qty and prior[item][1]:
			now_rate = val / qty
			old_rate = prior[item][0] / prior[item][1]
			if old_rate:
				change += (now_rate - old_rate) / old_rate * 100 * val
				weight += val
	return round(change / weight, 2) if weight else None
