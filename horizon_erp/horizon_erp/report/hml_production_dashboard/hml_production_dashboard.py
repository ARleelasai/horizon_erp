"""HML Production Dashboard.

* Work Orders in progress: % complete = completed operations (job cards) /
  total operations, blended with produced qty.
* Line utilisation over the period: logged job-card hours / usable hours.
* Schedule variance: completed WOs - actual end vs deadline (days, + = late);
  open WOs - days past deadline.
* Quality issues impacting the timeline: rework, audit hold, open NCs.
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, nowdate

from horizon_erp.constants import COMPANY
from horizon_erp.manufacturing.capacity import LINES, usable_hours_per_day


def execute(filters=None):
	filters = frappe._dict(filters or {})
	to_date = getdate(filters.to_date or nowdate())
	from_date = getdate(filters.from_date or add_days(to_date, -30))
	today = getdate(nowdate())
	wos = frappe.get_all(
		"Work Order",
		filters={"company": COMPANY, "docstatus": 1},
		fields=["name", "production_item", "qty", "produced_qty", "status", "hml_production_line", "hml_deadline",
			"actual_end_date", "hml_has_rework", "hml_audit_hold", "sales_order", "planned_start_date"],
		order_by="planned_start_date desc",
	)
	ops = {
		r.work_order: r
		for r in frappe.db.sql(
			"""select work_order, count(*) total, sum(case when docstatus = 1 then 1 else 0 end) done
			from `tabJob Card` where ifnull(is_corrective_job_card, 0) = 0 and docstatus < 2 group by work_order""",
			as_dict=True,
		)
	}
	nc = {
		r.hml_work_order: r.cnt
		for r in frappe.db.sql(
			"select hml_work_order, count(*) cnt from `tabNon Conformance` where status = 'Open' and ifnull(hml_work_order,'') != '' group by hml_work_order",
			as_dict=True,
		)
	}
	data = []
	for w in wos:
		o = ops.get(w.name)
		op_pct = (flt(o.done) / flt(o.total) * 100) if o and o.total else 0
		qty_pct = flt(w.produced_qty) / flt(w.qty) * 100 if w.qty else 0
		pct = 100 if w.status == "Completed" else round(max(qty_pct, op_pct * 0.95), 1)
		if w.status == "Completed" and w.actual_end_date and w.hml_deadline:
			variance = date_diff(getdate(w.actual_end_date), w.hml_deadline)
		elif w.hml_deadline:
			variance = max(date_diff(today, w.hml_deadline), 0)
		else:
			variance = None
		issues = []
		if w.hml_audit_hold:
			issues.append("Audit hold")
		if w.hml_has_rework:
			issues.append("Rework")
		if nc.get(w.name):
			issues.append(f"{nc[w.name]} open NC")
		if filters.only_open and w.status == "Completed":
			continue
		data.append(
			{
				"work_order": w.name,
				"item_code": w.production_item,
				"line": w.hml_production_line,
				"status": w.status,
				"qty": w.qty,
				"produced_qty": w.produced_qty,
				"pct_complete": pct,
				"deadline": w.hml_deadline,
				"schedule_variance_days": variance,
				"quality_issues": ", ".join(issues),
				"sales_order": w.sales_order,
			}
		)

	util = line_utilisation(from_date, to_date)
	columns = [
		{"label": _("Work Order"), "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 150},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Line"), "fieldname": "line", "fieldtype": "Data", "width": 100},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 60},
		{"label": _("Produced"), "fieldname": "produced_qty", "fieldtype": "Float", "width": 80},
		{"label": _("% Complete"), "fieldname": "pct_complete", "fieldtype": "Percent", "width": 95},
		{"label": _("Deadline"), "fieldname": "deadline", "fieldtype": "Date", "width": 100},
		{"label": _("Schedule Variance (days, + late)"), "fieldname": "schedule_variance_days", "fieldtype": "Int", "width": 120},
		{"label": _("Quality Issues"), "fieldname": "quality_issues", "fieldtype": "Data", "width": 180},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140},
	]
	chart = {
		"data": {"labels": [u["line"] for u in util], "datasets": [{"name": _("Utilisation %"), "values": [u["pct"] for u in util]}]},
		"type": "bar",
		"title": _("Line utilisation {0} to {1}").format(from_date, to_date),
	}
	summary = [{"label": _("{0} utilisation").format(u["line"]), "value": u["pct"], "datatype": "Percent", "indicator": "Blue"} for u in util]
	summary += [
		{"label": _("WOs in progress"), "value": len([d for d in data if d["status"] in ("In Process", "Not Started")]), "indicator": "Orange"},
		{"label": _("WOs late"), "value": len([d for d in data if (d["schedule_variance_days"] or 0) > 0]), "indicator": "Red"},
		{"label": _("WOs with quality issues"), "value": len([d for d in data if d["quality_issues"]]), "indicator": "Red"},
	]
	return columns, data, None, chart, summary


def line_utilisation(from_date, to_date):
	days = date_diff(to_date, from_date) + 1
	out = []
	for line in LINES.values():
		logged = frappe.db.sql(
			"""select sum(tl.time_in_mins) / 60 from `tabJob Card Time Log` tl join `tabJob Card` jc on jc.name = tl.parent
			where jc.workstation = %s and jc.docstatus = 1 and date(tl.from_time) between %s and %s""",
			(line, from_date, to_date),
		)[0][0]
		capacity = usable_hours_per_day(line) * days
		out.append({"line": line, "pct": round(flt(logged) / capacity * 100, 1) if capacity else 0})
	return out
