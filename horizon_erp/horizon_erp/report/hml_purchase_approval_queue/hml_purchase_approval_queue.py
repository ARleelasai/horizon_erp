"""HML Purchase Approval Queue - the Finance Director's approval dashboard.

Pending POs sorted by urgency, then amount (largest first), with hours in the
current state. More than 24 h = SLA breach (red), more than 48 h = will be /
was auto-escalated.
"""

import frappe
from frappe import _

from horizon_erp.setup.workflows import PO_STATE_ROLE
from horizon_erp.tasks.approvals import ESCALATE_AFTER_HOURS, REMIND_AFTER_HOURS, pending_purchase_orders

URGENCY_ORDER = {"Critical - Line Stoppage": 0, "Urgent": 1, "Normal": 2}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = pending_purchase_orders()
	if filters.state:
		rows = [r for r in rows if r.workflow_state == filters.state]
	data = []
	for r in sorted(rows, key=lambda r: (URGENCY_ORDER.get(r.hml_urgency, 3), -r.base_grand_total)):
		data.append(
			{
				"purchase_order": r.name,
				"supplier": r.supplier_name,
				"amount": r.base_grand_total,
				"urgency": r.hml_urgency,
				"tier": r.hml_approval_tier,
				"state": r.workflow_state,
				"waiting_for": PO_STATE_ROLE.get(r.workflow_state),
				"hours_pending": r.hours_pending,
				"sla": "Escalation due" if r.hours_pending > ESCALATE_AFTER_HOURS else ("Breached (> 24 h)" if r.hours_pending > REMIND_AFTER_HOURS else "Within SLA"),
				"created_by": r.owner,
			}
		)
	columns = [
		{"label": _("Purchase Order"), "fieldname": "purchase_order", "fieldtype": "Link", "options": "Purchase Order", "width": 150},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Data", "width": 180},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Urgency"), "fieldname": "urgency", "fieldtype": "Data", "width": 150},
		{"label": _("Tier"), "fieldname": "tier", "fieldtype": "Data", "width": 220},
		{"label": _("State"), "fieldname": "state", "fieldtype": "Data", "width": 160},
		{"label": _("Waiting For"), "fieldname": "waiting_for", "fieldtype": "Data", "width": 170},
		{"label": _("Hours Pending"), "fieldname": "hours_pending", "fieldtype": "Float", "precision": 1, "width": 110},
		{"label": _("SLA"), "fieldname": "sla", "fieldtype": "Data", "width": 140},
		{"label": _("Raised By"), "fieldname": "created_by", "fieldtype": "Link", "options": "User", "width": 180},
	]
	summary = [
		{"label": _("Pending POs"), "value": len(data), "indicator": "Blue"},
		{"label": _("Pending value"), "value": sum(d["amount"] for d in data), "datatype": "Currency", "indicator": "Blue"},
		{"label": _("SLA breached (> 24 h)"), "value": len([d for d in data if d["hours_pending"] > REMIND_AFTER_HOURS]), "indicator": "Red"},
		{"label": _("Blacklist exceptions (FY)"), "value": frappe.db.count("Supplier Blacklist Exception", {"event": "Approved by Finance Director"}), "indicator": "Orange"},
	]
	return columns, data, None, None, summary
