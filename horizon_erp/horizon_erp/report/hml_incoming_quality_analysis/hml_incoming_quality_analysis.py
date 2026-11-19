"""HML Incoming Quality Analysis (the Quality Dashboard for receipts).

Views:
* By Supplier       - lines inspected, failed, rejected qty, rejection rate
* By Item Category  - which material types fail most, with top reason
* Inspection SLA    - every inspection with hours from receipt; target 4 h
"""

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.constants import COMPANY

SLA_HOURS = 4


def execute(filters=None):
	filters = frappe._dict(filters or {})
	view = filters.view or "By Supplier"
	rows = frappe.db.sql(
		"""
		select qi.name, qi.hml_supplier as supplier, s.supplier_name, i.item_group, qi.item_code,
			qi.hml_result as result, qi.hml_rejection_reason as reason, qi.hml_rejected_qty as rejected_qty,
			qi.hml_inspection_hours as hours, qi.hml_sla_met as sla_met, qi.hml_received_at as received_at,
			pri.received_qty
		from `tabQuality Inspection` qi
		join `tabPurchase Receipt` pr on pr.name = qi.reference_name and qi.reference_type = 'Purchase Receipt'
		left join `tabPurchase Receipt Item` pri on pri.name = qi.child_row_reference
		join `tabItem` i on i.name = qi.item_code
		left join `tabSupplier` s on s.name = qi.hml_supplier
		where qi.docstatus = 1 and pr.company = %(company)s
			and pr.posting_date between %(from_date)s and %(to_date)s
		""",
		{"company": COMPANY, "from_date": filters.from_date or "2026-04-01", "to_date": filters.to_date or "2099-12-31"},
		as_dict=True,
	)
	if view == "Inspection SLA":
		return sla_view(rows)
	key = "supplier_name" if view == "By Supplier" else "item_group"
	return group_view(rows, key, view)


def group_view(rows, key, view):
	groups = {}
	for r in rows:
		g = groups.setdefault(
			r[key] or "-",
			{"group": r[key] or "-", "inspections": 0, "failed": 0, "conditional": 0, "received_qty": 0, "rejected_qty": 0, "reasons": {}},
		)
		g["inspections"] += 1
		g["received_qty"] += flt(r.received_qty)
		if r.result in ("Fail", "Rework"):
			g["failed"] += 1
			g["rejected_qty"] += flt(r.rejected_qty)
			g["reasons"][r.reason] = g["reasons"].get(r.reason, 0) + 1
		elif r.result == "Conditional Pass":
			g["conditional"] += 1
	data = []
	for g in groups.values():
		g["fail_rate"] = g["failed"] / g["inspections"] * 100 if g["inspections"] else 0
		g["rejection_rate"] = g["rejected_qty"] / g["received_qty"] * 100 if g["received_qty"] else 0
		g["top_reason"] = max(g["reasons"], key=g["reasons"].get) if g["reasons"] else None
		g.pop("reasons")
		data.append(g)
	data.sort(key=lambda d: -d["rejection_rate"])
	columns = [
		{"label": _("Supplier") if view == "By Supplier" else _("Item Category"), "fieldname": "group", "fieldtype": "Data", "width": 200},
		{"label": _("Inspections"), "fieldname": "inspections", "fieldtype": "Int", "width": 100},
		{"label": _("Failed"), "fieldname": "failed", "fieldtype": "Int", "width": 80},
		{"label": _("Conditional Pass"), "fieldname": "conditional", "fieldtype": "Int", "width": 120},
		{"label": _("Received Qty"), "fieldname": "received_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Rejected Qty"), "fieldname": "rejected_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Rejection Rate %"), "fieldname": "rejection_rate", "fieldtype": "Percent", "width": 120},
		{"label": _("Inspection Fail %"), "fieldname": "fail_rate", "fieldtype": "Percent", "width": 120},
		{"label": _("Top Reason"), "fieldname": "top_reason", "fieldtype": "Data", "width": 220},
	]
	chart = {
		"data": {"labels": [d["group"] for d in data], "datasets": [{"name": _("Rejection Rate %"), "values": [round(d["rejection_rate"], 2) for d in data]}]},
		"type": "bar",
		"colors": ["#e24c4c"],
	}
	return columns, data, None, chart


def sla_view(rows):
	data = [
		{
			"inspection": r.name,
			"supplier": r.supplier_name,
			"item_code": r.item_code,
			"result": r.result,
			"received_at": r.received_at,
			"hours": flt(r.hours),
			"sla_met": r.sla_met,
		}
		for r in sorted(rows, key=lambda r: -flt(r.hours))
	]
	met = len([d for d in data if d["sla_met"]])
	columns = [
		{"label": _("Inspection"), "fieldname": "inspection", "fieldtype": "Link", "options": "Quality Inspection", "width": 160},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Data", "width": 180},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("Result"), "fieldname": "result", "fieldtype": "Data", "width": 120},
		{"label": _("Received At"), "fieldname": "received_at", "fieldtype": "Datetime", "width": 160},
		{"label": _("Hours to Inspect"), "fieldname": "hours", "fieldtype": "Float", "precision": 1, "width": 120},
		{"label": _("Within 4 h"), "fieldname": "sla_met", "fieldtype": "Check", "width": 90},
	]
	summary = [
		{"label": _("Inspections"), "value": len(data), "indicator": "Blue"},
		{"label": _("SLA compliance"), "value": round(met / len(data) * 100, 1) if data else 0, "datatype": "Percent", "indicator": "Green" if data and met / len(data) >= 0.9 else "Red"},
	]
	return columns, data, None, None, summary
