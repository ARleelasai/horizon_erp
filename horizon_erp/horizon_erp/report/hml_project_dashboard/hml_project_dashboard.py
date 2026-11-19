"""HML Project Dashboard.

Task rows: budgeted hours (Task.expected_time) vs actual (timesheets), hour
variance, budgeted vs actual cost, % complete vs % of planned time elapsed
(schedule variance: + = behind plan), milestone billing status.
Project summary: budget vs actual cost, margin realised vs budgeted.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

from horizon_erp.constants import COMPANY
from horizon_erp.overrides.projects import project_costs


def execute(filters=None):
	filters = frappe._dict(filters or {})
	project = filters.project or frappe.db.get_value("Project", {"company": COMPANY, "status": "Open"})
	if not project:
		return [], []
	today = getdate(nowdate())
	p = frappe.get_doc("Project", project)
	tasks = frappe.get_all(
		"Task",
		filters={"project": project},
		fields=["name", "subject", "status", "progress", "expected_time", "actual_time", "exp_start_date", "exp_end_date",
			"hml_budgeted_cost", "total_costing_amount", "is_milestone", "hml_billing_pct", "hml_milestone_invoice"],
		order_by="exp_start_date",
	)
	data = []
	for t in tasks:
		span = date_diff(t.exp_end_date, t.exp_start_date) + 1 if t.exp_start_date and t.exp_end_date else 0
		elapsed = min(max(date_diff(today, t.exp_start_date) + 1, 0), span) if span else 0
		planned_pct = elapsed / span * 100 if span else 0
		done_pct = 100 if t.status == "Completed" else flt(t.progress)
		data.append(
			{
				"task": t.name,
				"subject": t.subject,
				"status": t.status,
				"budget_hours": t.expected_time,
				"actual_hours": t.actual_time,
				"hour_variance": flt(t.actual_time) - flt(t.expected_time),
				"budget_cost": t.hml_budgeted_cost,
				"actual_cost": t.total_costing_amount,
				"pct_complete": done_pct,
				"pct_planned": round(planned_pct, 1),
				"schedule_variance": round(planned_pct - done_pct, 1),
				"milestone": f"{t.hml_billing_pct:g} %" if t.is_milestone and t.hml_billing_pct else "",
				"invoice": t.hml_milestone_invoice,
			}
		)
	costs = project_costs(project)
	budget_total = flt(p.estimated_costing) * (1 + flt(p.hml_overhead_pct) / 100)
	summary = [
		{"label": _("Contract value"), "value": p.hml_contract_value, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Budget cost (incl. overhead)"), "value": budget_total, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Actual cost to date"), "value": costs.total, "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Billed (milestones)"), "value": p.hml_billed_amount, "datatype": "Currency", "indicator": "Green"},
		{"label": _("Margin realised %"), "value": p.hml_margin_pct, "datatype": "Percent", "indicator": "Green"},
		{"label": _("Margin budgeted %"), "value": p.hml_budget_margin_pct, "datatype": "Percent", "indicator": "Blue"},
	]
	columns = [
		{"label": _("Task"), "fieldname": "task", "fieldtype": "Link", "options": "Task", "width": 130},
		{"label": _("Subject"), "fieldname": "subject", "fieldtype": "Data", "width": 220},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
		{"label": _("Budget h"), "fieldname": "budget_hours", "fieldtype": "Float", "width": 85},
		{"label": _("Actual h"), "fieldname": "actual_hours", "fieldtype": "Float", "width": 85},
		{"label": _("Hour Variance"), "fieldname": "hour_variance", "fieldtype": "Float", "width": 100},
		{"label": _("Budget Cost"), "fieldname": "budget_cost", "fieldtype": "Currency", "width": 110},
		{"label": _("Actual Cost"), "fieldname": "actual_cost", "fieldtype": "Currency", "width": 110},
		{"label": _("% Complete"), "fieldname": "pct_complete", "fieldtype": "Percent", "width": 95},
		{"label": _("% Time Elapsed"), "fieldname": "pct_planned", "fieldtype": "Percent", "width": 110},
		{"label": _("Schedule Variance (pts, + behind)"), "fieldname": "schedule_variance", "fieldtype": "Float", "width": 130},
		{"label": _("Milestone"), "fieldname": "milestone", "fieldtype": "Data", "width": 80},
		{"label": _("Invoice"), "fieldname": "invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 130},
	]
	chart = {
		"data": {
			"labels": [d["subject"][:22] for d in data],
			"datasets": [{"name": _("Budget h"), "values": [flt(d["budget_hours"]) for d in data]},
				{"name": _("Actual h"), "values": [flt(d["actual_hours"]) for d in data]}],
		},
		"type": "bar",
	}
	return columns, data, None, chart, summary
