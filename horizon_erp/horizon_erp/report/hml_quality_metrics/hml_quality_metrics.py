"""HML Quality Metrics.

* First-pass yield (FPY) per item = completed WOs without rework / completed WOs.
* Rework cost % = corrective (rework) operation cost / total production cost
  (value of finished goods from Manufacture entries).
* Defect reasons by month: failed inspections (incoming + in-process) and
  non-conformances, grouped by rejection reason - the trend chart shows
  whether the same defects keep coming back.
"""

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.constants import COMPANY


def execute(filters=None):
	filters = frappe._dict(filters or {})
	view = filters.view or "First-Pass Yield"
	if view == "Defect Trend":
		return defect_trend(filters)
	return fpy(filters)


def fpy(filters):
	rows = frappe.db.sql(
		"""select wo.production_item item, count(*) completed,
			sum(case when wo.hml_has_rework = 1 then 0 else 1 end) first_pass,
			sum(wo.corrective_operation_cost) rework_cost,
			sum((select sum(sed.amount) from `tabStock Entry Detail` sed join `tabStock Entry` se on se.name = sed.parent
				where se.work_order = wo.name and se.purpose = 'Manufacture' and se.docstatus = 1 and sed.is_finished_item = 1)) production_cost
		from `tabWork Order` wo
		where wo.company = %s and wo.status = 'Completed'
		group by wo.production_item""",
		COMPANY,
		as_dict=True,
	)
	data = []
	for r in rows:
		data.append(
			{
				"item_code": r.item,
				"completed": r.completed,
				"first_pass": r.first_pass,
				"fpy": flt(r.first_pass) / flt(r.completed) * 100 if r.completed else 0,
				"rework_cost": flt(r.rework_cost),
				"production_cost": flt(r.production_cost),
				"rework_pct": flt(r.rework_cost) / flt(r.production_cost) * 100 if r.production_cost else 0,
			}
		)
	tot_c = sum(d["completed"] for d in data)
	tot_fp = sum(d["first_pass"] for d in data)
	tot_rw = sum(d["rework_cost"] for d in data)
	tot_pc = sum(d["production_cost"] for d in data)
	columns = [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Completed WOs"), "fieldname": "completed", "fieldtype": "Int", "width": 110},
		{"label": _("Without Rework"), "fieldname": "first_pass", "fieldtype": "Int", "width": 110},
		{"label": _("First-Pass Yield %"), "fieldname": "fpy", "fieldtype": "Percent", "width": 130},
		{"label": _("Rework Cost"), "fieldname": "rework_cost", "fieldtype": "Currency", "width": 120},
		{"label": _("Production Cost"), "fieldname": "production_cost", "fieldtype": "Currency", "width": 130},
		{"label": _("Rework % of Cost"), "fieldname": "rework_pct", "fieldtype": "Percent", "width": 120},
	]
	summary = [
		{"label": _("First-pass yield"), "value": round(tot_fp / tot_c * 100, 1) if tot_c else 0, "datatype": "Percent", "indicator": "Green"},
		{"label": _("Rework cost"), "value": tot_rw, "datatype": "Currency", "indicator": "Red"},
		{"label": _("Rework % of production cost"), "value": round(tot_rw / tot_pc * 100, 2) if tot_pc else 0, "datatype": "Percent", "indicator": "Red"},
	]
	return columns, data, None, None, summary


def defect_trend(filters):
	rows = frappe.db.sql(
		"""select date_format(qi.report_date, '%%Y-%%m') ym, ifnull(qi.hml_rejection_reason, 'Unspecified') reason, count(*) cnt
		from `tabQuality Inspection` qi where qi.docstatus = 1 and qi.hml_result in ('Fail', 'Rework')
		group by ym, reason
		union all
		select date_format(nc.creation, '%%Y-%%m') ym, ifnull(nc.hml_defect_reason, 'Unspecified') reason, count(*) cnt
		from `tabNon Conformance` nc where nc.hml_company = %s and nc.hml_source in ('Customer Complaint', 'Production Audit')
		group by ym, reason""",
		COMPANY,
		as_dict=True,
	)
	months = sorted({r.ym for r in rows})
	reasons = {}
	for r in rows:
		reasons.setdefault(r.reason, {"reason": r.reason, "total": 0})
		reasons[r.reason][r.ym] = reasons[r.reason].get(r.ym, 0) + r.cnt
		reasons[r.reason]["total"] += r.cnt
	data = sorted(reasons.values(), key=lambda d: -d["total"])
	columns = [{"label": _("Defect Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 260}]
	columns += [{"label": m, "fieldname": m, "fieldtype": "Int", "width": 80} for m in months]
	columns.append({"label": _("Total"), "fieldname": "total", "fieldtype": "Int", "width": 70})
	chart = {
		"data": {"labels": months, "datasets": [{"name": d["reason"], "values": [d.get(m, 0) for m in months]} for d in data[:5]]},
		"type": "bar",
		"barOptions": {"stacked": 1},
	}
	return columns, data, None, chart
