"""Purchase Order approval SLA: reminders and auto-escalation.

* send_approval_reminders (cron every 6 h): a PO waiting > 24 h in a pending
  state emails every user holding that state's role.
* escalate_stale_approvals (hourly): a PO waiting > 48 h in a pending state is
  moved to the next approval level (Dept Head -> Procurement -> Finance
  Director) with a comment, so one absent approver cannot block purchasing.
  At Finance Director level there is no higher level; the System Manager is
  alerted instead.

The first "approval requested" email is Frappe's standard workflow-action
email (Workflow.send_email_alert = 1).
"""

import frappe
from frappe.utils import get_url_to_form, now_datetime, time_diff_in_hours

from horizon_erp.constants import COMPANY
from horizon_erp.notify import notify
from horizon_erp.setup.workflows import PO_NEXT_STATE, PO_PENDING_STATES, PO_STATE_ROLE

REMIND_AFTER_HOURS = 24
ESCALATE_AFTER_HOURS = 48


def pending_purchase_orders():
	rows = frappe.get_all(
		"Purchase Order",
		filters={"company": COMPANY, "docstatus": 0, "workflow_state": ("in", PO_PENDING_STATES)},
		fields=["name", "supplier_name", "base_grand_total", "workflow_state", "hml_state_since", "modified",
			"hml_urgency", "hml_approval_tier", "owner"],
	)
	now = now_datetime()
	for r in rows:
		r.hours_pending = round(time_diff_in_hours(now, r.hml_state_since or r.modified), 1)
	return rows


def users_with_role(role):
	return [
		u
		for u in frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
		if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")
	]


def send_approval_reminders():
	for po in pending_purchase_orders():
		if po.hours_pending <= REMIND_AFTER_HOURS:
			continue
		recipients = users_with_role(PO_STATE_ROLE[po.workflow_state])
		if not recipients:
			continue
		notify(
			recipients=recipients,
			subject=f"Reminder: PO {po.name} waiting {int(po.hours_pending)} h for your approval",
			message=(
				f"<p>Purchase Order <a href='{get_url_to_form('Purchase Order', po.name)}'>{po.name}</a> "
				f"({po.supplier_name}, Rs {po.base_grand_total:,.0f}, urgency {po.hml_urgency}) has been in "
				f"<b>{po.workflow_state}</b> for {po.hours_pending} hours.</p>"
				f"<p>It will be escalated to the next approval level after {ESCALATE_AFTER_HOURS} hours.</p>"
			),
			reference_doctype="Purchase Order",
			reference_name=po.name,
		)


def escalate_stale_approvals():
	escalated = []
	for po in pending_purchase_orders():
		if po.hours_pending <= ESCALATE_AFTER_HOURS:
			continue
		nxt = PO_NEXT_STATE.get(po.workflow_state)
		doc = frappe.get_doc("Purchase Order", po.name)
		if not nxt:
			notify(
				recipients=users_with_role("System Manager"),
				subject=f"PO {po.name} stuck at Finance Director for {int(po.hours_pending)} h",
				message=f"No higher approval level exists. Please follow up on {get_url_to_form('Purchase Order', po.name)}.",
				reference_doctype="Purchase Order",
				reference_name=po.name,
			)
			continue
		doc.db_set(
			{
				"workflow_state": nxt,
				"hml_state_since": now_datetime(),
				"hml_escalation_count": (doc.hml_escalation_count or 0) + 1,
			}
		)
		doc.add_comment(
			"Comment",
			f"Auto-escalated from {po.workflow_state} to {nxt}: no decision within {ESCALATE_AFTER_HOURS} hours "
			f"({po.hours_pending} h).",
		)
		escalated.append(po.name)
		notify(
			recipients=users_with_role(PO_STATE_ROLE[nxt]),
			subject=f"Escalated: PO {po.name} needs your approval",
			message=(
				f"<p>{po.name} ({po.supplier_name}, Rs {po.base_grand_total:,.0f}) was not actioned at "
				f"{po.workflow_state} within {ESCALATE_AFTER_HOURS} h and has been escalated to you.</p>"
			),
			reference_doctype="Purchase Order",
			reference_name=po.name,
		)
	return escalated
