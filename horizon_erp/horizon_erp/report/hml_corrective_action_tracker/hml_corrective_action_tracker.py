"""HML Corrective Action Tracker - due vs overdue, by owner, with training needs."""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	today = getdate(nowdate())
	conditions = {}
	if not filters.include_closed:
		conditions["status"] = ("in", ["Open", "In Progress"])
	if filters.owner_user:
		conditions["owner_user"] = filters.owner_user
	rows = frappe.get_all(
		"Corrective Action",
		filters=conditions,
		fields=["name", "title", "source", "status", "owner_user", "due_date", "creation", "training_required", "training_topic",
			"work_order", "supplier", "production_audit", "non_conformance", "completed_on"],
		order_by="due_date asc",
	)
	data = []
	for r in rows:
		open_ = r.status in ("Open", "In Progress")
		overdue = open_ and getdate(r.due_date) < today
		data.append(
			{
				**r,
				"bucket": "Overdue" if overdue else ("Due in 7 days" if open_ and date_diff(r.due_date, today) <= 7 else ("Open" if open_ else "Closed")),
				"days_open": date_diff(r.completed_on or today, getdate(r.creation)),
				"days_overdue": date_diff(today, r.due_date) if overdue else 0,
				"linked_to": r.production_audit or r.non_conformance or r.work_order or r.supplier,
			}
		)
	columns = [
		{"label": _("Corrective Action"), "fieldname": "name", "fieldtype": "Link", "options": "Corrective Action", "width": 140},
		{"label": _("Title"), "fieldname": "title", "fieldtype": "Data", "width": 260},
		{"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 130},
		{"label": _("Owner"), "fieldname": "owner_user", "fieldtype": "Link", "options": "User", "width": 190},
		{"label": _("Due"), "fieldname": "due_date", "fieldtype": "Date", "width": 95},
		{"label": _("Bucket"), "fieldname": "bucket", "fieldtype": "Data", "width": 110},
		{"label": _("Days Overdue"), "fieldname": "days_overdue", "fieldtype": "Int", "width": 95},
		{"label": _("Days Open"), "fieldname": "days_open", "fieldtype": "Int", "width": 85},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 95},
		{"label": _("Training Needed"), "fieldname": "training_required", "fieldtype": "Check", "width": 100},
		{"label": _("Training Topic"), "fieldname": "training_topic", "fieldtype": "Data", "width": 220},
		{"label": _("Linked To"), "fieldname": "linked_to", "fieldtype": "Data", "width": 160},
	]
	summary = [
		{"label": _("Open"), "value": len([d for d in data if d["bucket"] != "Closed"]), "indicator": "Blue"},
		{"label": _("Overdue"), "value": len([d for d in data if d["bucket"] == "Overdue"]), "indicator": "Red"},
		{"label": _("Due in 7 days"), "value": len([d for d in data if d["bucket"] == "Due in 7 days"]), "indicator": "Orange"},
		{"label": _("Training needs"), "value": len([d for d in data if d["training_required"]]), "indicator": "Purple"},
	]
	by_owner = {}
	for d in data:
		by_owner[d["owner_user"]] = by_owner.get(d["owner_user"], 0) + 1
	chart = {"data": {"labels": list(by_owner), "datasets": [{"name": _("Actions"), "values": list(by_owner.values())}]}, "type": "bar"}
	return columns, data, None, chart, summary
