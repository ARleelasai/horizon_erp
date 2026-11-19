"""HML Approval Audit Report - every approval step, who, when, how long.

Built from the document Version log (workflow_state changes), so it cannot be
edited by users. Blacklist overrides and auto-escalations are flagged.
"""

import json

import frappe
from frappe import _
from frappe.utils import get_datetime, time_diff_in_hours

from horizon_erp.constants import COMPANY


def execute(filters=None):
	filters = frappe._dict(filters or {})
	po_filters = {"company": COMPANY}
	if filters.from_date:
		po_filters["transaction_date"] = (">=", filters.from_date)
	pos = {
		p.name: p
		for p in frappe.get_all(
			"Purchase Order",
			filters=po_filters,
			fields=["name", "supplier_name", "base_grand_total", "hml_approval_tier", "hml_supplier_blacklisted", "creation", "owner"],
		)
	}
	if not pos:
		return get_columns(), []
	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": "Purchase Order", "docname": ("in", list(pos))},
		fields=["docname", "data", "owner", "creation"],
		order_by="docname, creation",
	)
	escalations = {
		(c.reference_name, str(c.creation)[:16])
		for c in frappe.get_all(
			"Comment",
			filters={"reference_doctype": "Purchase Order", "content": ("like", "Auto-escalated%")},
			fields=["reference_name", "creation"],
		)
	}
	data = []
	last_time = {}
	for v in versions:
		try:
			changed = json.loads(v.data).get("changed") or []
		except Exception:
			continue
		for field, old, new in changed:
			if field != "workflow_state":
				continue
			po = pos[v.docname]
			start = last_time.get(v.docname, po.creation)
			data.append(
				{
					"purchase_order": v.docname,
					"supplier": po.supplier_name,
					"amount": po.base_grand_total,
					"tier": po.hml_approval_tier,
					"from_state": old or "Draft",
					"to_state": new,
					"action_by": v.owner,
					"action_at": v.creation,
					"hours_in_previous_state": round(time_diff_in_hours(v.creation, start), 1),
					"blacklist_exception": po.hml_supplier_blacklisted,
					"auto_escalated": 1 if (v.docname, str(v.creation)[:16]) in escalations else 0,
				}
			)
			last_time[v.docname] = get_datetime(v.creation)
	if filters.purchase_order:
		data = [d for d in data if d["purchase_order"] == filters.purchase_order]
	return get_columns(), data


def get_columns():
	return [
		{"label": _("Purchase Order"), "fieldname": "purchase_order", "fieldtype": "Link", "options": "Purchase Order", "width": 150},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Data", "width": 170},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 115},
		{"label": _("Tier"), "fieldname": "tier", "fieldtype": "Data", "width": 120},
		{"label": _("From"), "fieldname": "from_state", "fieldtype": "Data", "width": 150},
		{"label": _("To"), "fieldname": "to_state", "fieldtype": "Data", "width": 160},
		{"label": _("By"), "fieldname": "action_by", "fieldtype": "Link", "options": "User", "width": 190},
		{"label": _("At"), "fieldname": "action_at", "fieldtype": "Datetime", "width": 160},
		{"label": _("Hours in Previous State"), "fieldname": "hours_in_previous_state", "fieldtype": "Float", "precision": 1, "width": 120},
		{"label": _("Blacklist Exception"), "fieldname": "blacklist_exception", "fieldtype": "Check", "width": 90},
		{"label": _("Auto-escalated"), "fieldname": "auto_escalated", "fieldtype": "Check", "width": 90},
	]
