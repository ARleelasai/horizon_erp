"""Production Audit gate on Work Order completion."""

import frappe
from frappe import _

from horizon_erp.constants import is_hml

CRITICAL = 70


def blocking_audits(work_order):
	"""Submitted audits < 70 whose corrective action is not done and audit not closed."""
	out = []
	for a in frappe.get_all(
		"Production Audit",
		filters={"work_order": work_order, "docstatus": 1, "audit_score": ("<", CRITICAL)},
		fields=["name", "audit_score", "corrective_action", "workflow_state"],
	):
		if a.workflow_state == "Action Closed":
			continue
		ca_status = frappe.db.get_value("Corrective Action", a.corrective_action, "status") if a.corrective_action else None
		if ca_status in ("Completed", "Verified"):
			continue
		out.append(a)
	return out


def release_audit_hold(audit_name, force=False):
	wo = frappe.db.get_value("Production Audit", audit_name, "work_order")
	if wo and (force or not blocking_audits(wo)):
		frappe.db.set_value("Work Order", wo, "hml_audit_hold", 0)


def validate_manufacture_entry(doc, method=None):
	"""Stock Entry (Manufacture) for a HML Work Order: blocked while an audit < 70 is open."""
	if not is_hml(doc) or doc.purpose != "Manufacture" or not doc.work_order:
		return
	blocking = blocking_audits(doc.work_order)
	if blocking:
		lines = "<br>".join(
			f"{a.name}: score {a.audit_score}, corrective action {a.corrective_action or '-'}" for a in blocking
		)
		frappe.throw(
			_("Work Order {0} cannot be completed: production audit below 70 with open corrective action.<br>{1}").format(
				doc.work_order, lines
			),
			title=_("Rework required before completion"),
		)
