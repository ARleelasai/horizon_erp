"""HML Audit Trail - what changed, who, when (transaction level).

Built on Frappe's Version log (immutable from the UI): creation, field
changes (old -> new), child-row changes, submit / cancel and workflow moves,
for Horizon transactions. Filter by document type, user and dates.
"""

import json

import frappe
from frappe import _

from horizon_erp.constants import COMPANY

DEFAULT_DOCTYPES = ["Sales Order", "Sales Invoice", "Purchase Order", "Purchase Invoice", "Payment Entry", "Journal Entry",
	"Quotation", "Delivery Note", "Purchase Receipt", "Stock Entry", "Work Order", "Budget", "Item Price", "Pricing Rule",
	"Supplier", "Customer", "Asset", "Salary Slip"]
DOCSTATUS = {0: "Draft", 1: "Submitted", 2: "Cancelled"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	doctypes = [filters.ref_doctype] if filters.ref_doctype else DEFAULT_DOCTYPES
	cond = {"ref_doctype": ("in", doctypes), "creation": ("between", [filters.from_date or "2026-04-01", (filters.to_date or "2099-12-31") + " 23:59:59"])}
	if filters.user:
		cond["owner"] = filters.user
	versions = frappe.get_all("Version", filters=cond, fields=["name", "ref_doctype", "docname", "owner", "creation", "data"],
		order_by="creation desc", limit=int(filters.limit or 1000))
	company_of = {}
	data = []
	for v in versions:
		key = (v.ref_doctype, v.docname)
		if key not in company_of:
			meta = frappe.get_meta(v.ref_doctype)
			company_of[key] = frappe.db.get_value(v.ref_doctype, v.docname, "company") if meta.has_field("company") else COMPANY
		if company_of[key] and company_of[key] != COMPANY:
			continue
		try:
			d = json.loads(v.data or "{}")
		except Exception:
			d = {}
		changed = d.get("changed") or []
		action, details = "Updated", []
		for field, old, new in changed:
			if field == "docstatus":
				action = {1: "Submitted", 2: "Cancelled"}.get(new, "Updated")
			elif field == "workflow_state":
				action = f"Workflow: {old or 'Draft'} -> {new}"
			elif field not in ("modified", "modified_by"):
				details.append(f"{field}: {old} -> {new}")
		if d.get("creation"):
			action = "Created"
		for k in ("added", "removed", "row_changed"):
			if d.get(k):
				details.append(f"{len(d[k])} row(s) {k.replace('_', ' ')}")
		data.append({"timestamp": v.creation, "user": v.owner, "doctype": v.ref_doctype, "document": v.docname,
			"action": action, "details": "; ".join(details)[:500], "version": v.name})
	cols = [
		{"label": _("When"), "fieldname": "timestamp", "fieldtype": "Datetime", "width": 160},
		{"label": _("User"), "fieldname": "user", "fieldtype": "Link", "options": "User", "width": 190},
		{"label": _("Document Type"), "fieldname": "doctype", "fieldtype": "Data", "width": 130},
		{"label": _("Document"), "fieldname": "document", "fieldtype": "Dynamic Link", "options": "doctype", "width": 160},
		{"label": _("Action"), "fieldname": "action", "fieldtype": "Data", "width": 230},
		{"label": _("What Changed (old -> new)"), "fieldname": "details", "fieldtype": "Data", "width": 420},
		{"label": _("Version"), "fieldname": "version", "fieldtype": "Link", "options": "Version", "width": 100},
	]
	return cols, data
