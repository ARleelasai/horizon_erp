"""Audit Findings Dashboard (Production Audit).

Views:
* Recent Audits     - latest audits with score, band and the 3-audit moving
                      average per line (trend).
* Low-Scoring Lines - machines / lines whose average is below 80 or that had
                      2+ critical audits: consistently low scores.
* Pending Actions   - corrective actions raised by audits that are not done.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	view = filters.view or "Recent Audits"
	from_date = filters.from_date or add_days(nowdate(), -90)
	audits = frappe.get_all(
		"Production Audit",
		filters={"docstatus": 1, "audit_date": (">=", from_date)},
		fields=["name", "audit_date", "work_order", "production_item", "production_line", "inspector", "audit_score",
			"score_band", "workflow_state", "corrective_action"],
		order_by="audit_date asc, creation asc",
	)
	if view == "Low-Scoring Lines":
		return low_lines(audits)
	if view == "Pending Actions":
		return pending_actions()
	history, data = {}, []
	for a in audits:
		h = history.setdefault(a.production_line or "-", [])
		h.append(a.audit_score)
		data.append({**a, "moving_avg": round(sum(h[-3:]) / len(h[-3:]), 1)})
	data.reverse()
	columns = [
		{"label": _("Audit"), "fieldname": "name", "fieldtype": "Link", "options": "Production Audit", "width": 130},
		{"label": _("Date"), "fieldname": "audit_date", "fieldtype": "Date", "width": 95},
		{"label": _("Work Order"), "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 150},
		{"label": _("Product"), "fieldname": "production_item", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Line"), "fieldname": "production_line", "fieldtype": "Data", "width": 100},
		{"label": _("Score"), "fieldname": "audit_score", "fieldtype": "Int", "width": 70},
		{"label": _("Band"), "fieldname": "score_band", "fieldtype": "Data", "width": 130},
		{"label": _("Line 3-audit Avg"), "fieldname": "moving_avg", "fieldtype": "Float", "width": 120},
		{"label": _("State"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 110},
		{"label": _("Corrective Action"), "fieldname": "corrective_action", "fieldtype": "Link", "options": "Corrective Action", "width": 140},
	]
	chart = {
		"data": {"labels": [str(a.audit_date) for a in audits], "datasets": [{"name": _("Score"), "values": [a.audit_score for a in audits]}]},
		"type": "line",
		"yMarkers": [{"label": "70", "value": 70}],
	}
	summary = [
		{"label": _("Audits"), "value": len(audits), "indicator": "Blue"},
		{"label": _("Average score"), "value": round(sum(a.audit_score for a in audits) / len(audits), 1) if audits else 0, "indicator": "Blue"},
		{"label": _("Critical (< 70)"), "value": len([a for a in audits if a.audit_score < 70]), "indicator": "Red"},
	]
	return columns, data, None, chart, summary


def low_lines(audits):
	lines = {}
	for a in audits:
		l = lines.setdefault(a.production_line or "-", {"line": a.production_line or "-", "audits": 0, "total": 0, "critical": 0, "lowest": 100})
		l["audits"] += 1
		l["total"] += a.audit_score
		l["critical"] += 1 if a.audit_score < 70 else 0
		l["lowest"] = min(l["lowest"], a.audit_score)
	data = []
	for l in lines.values():
		l["average"] = round(l["total"] / l["audits"], 1)
		l["flag"] = "Consistently low" if (l["average"] < 80 or l["critical"] >= 2) else "OK"
		data.append(l)
	data.sort(key=lambda d: d["average"])
	columns = [
		{"label": _("Line / Machine"), "fieldname": "line", "fieldtype": "Data", "width": 150},
		{"label": _("Audits"), "fieldname": "audits", "fieldtype": "Int", "width": 80},
		{"label": _("Average Score"), "fieldname": "average", "fieldtype": "Float", "width": 110},
		{"label": _("Lowest"), "fieldname": "lowest", "fieldtype": "Int", "width": 80},
		{"label": _("Critical Audits"), "fieldname": "critical", "fieldtype": "Int", "width": 110},
		{"label": _("Flag"), "fieldname": "flag", "fieldtype": "Data", "width": 150},
	]
	return columns, data


def pending_actions():
	rows = frappe.db.sql(
		"""select ca.name, ca.title, ca.owner_user, ca.due_date, ca.status, ca.is_overdue, pa.name audit, pa.audit_score, pa.work_order
		from `tabCorrective Action` ca join `tabProduction Audit` pa on pa.name = ca.production_audit
		where ca.status in ('Open', 'In Progress') order by ca.due_date""",
		as_dict=True,
	)
	columns = [
		{"label": _("Corrective Action"), "fieldname": "name", "fieldtype": "Link", "options": "Corrective Action", "width": 140},
		{"label": _("Title"), "fieldname": "title", "fieldtype": "Data", "width": 260},
		{"label": _("Owner"), "fieldname": "owner_user", "fieldtype": "Link", "options": "User", "width": 180},
		{"label": _("Due"), "fieldname": "due_date", "fieldtype": "Date", "width": 95},
		{"label": _("Overdue"), "fieldname": "is_overdue", "fieldtype": "Check", "width": 75},
		{"label": _("Audit"), "fieldname": "audit", "fieldtype": "Link", "options": "Production Audit", "width": 130},
		{"label": _("Score"), "fieldname": "audit_score", "fieldtype": "Int", "width": 65},
		{"label": _("Work Order (on hold)"), "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 160},
	]
	return columns, rows
