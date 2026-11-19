"""Workflows and notifications, created idempotently on migrate.

Frappe workflows are per DocType, not per company. Every HML workflow therefore
has a plain "Submit"/"Approve" path for other companies (condition
`doc.company != HML`), so Leelas documents are not blocked by Horizon rules.
"""

import frappe

from horizon_erp.constants import COMPANY

HML = f'doc.company == "{COMPANY}"'
NOT_HML = f'doc.company != "{COMPANY}"'


def ensure_states(states):
	for name, style in states:
		if not frappe.db.exists("Workflow State", name):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": name, "style": style}).insert(
				ignore_permissions=True
			)


def ensure_actions(actions):
	for name in actions:
		if not frappe.db.exists("Workflow Action Master", name):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": name}).insert(
				ignore_permissions=True
			)


def upsert_workflow(name, document_type, states, transitions, send_email_alert=1):
	"""Create or fully replace a workflow definition.

	states: list of (state, doc_status, allow_edit_role, update_field, update_value)
	transitions: list of (state, action, next_state, allowed_role, condition, allow_self_approval)
	"""
	if frappe.db.exists("Workflow", name):
		wf = frappe.get_doc("Workflow", name)
		wf.states = []
		wf.transitions = []
	else:
		wf = frappe.new_doc("Workflow")
		wf.workflow_name = name
	wf.document_type = document_type
	wf.workflow_state_field = "workflow_state"
	wf.is_active = 1
	wf.override_status = 0
	wf.send_email_alert = send_email_alert
	for state, doc_status, role, update_field, update_value in states:
		wf.append(
			"states",
			{
				"state": state,
				"doc_status": str(doc_status),
				"allow_edit": role,
				"update_field": update_field,
				"update_value": update_value,
			},
		)
	for state, action, next_state, role, condition, self_approval in transitions:
		wf.append(
			"transitions",
			{
				"state": state,
				"action": action,
				"next_state": next_state,
				"allowed": role,
				"condition": condition,
				"allow_self_approval": self_approval,
			},
		)
	wf.save(ignore_permissions=True)
	return wf


def make_quotation_workflow():
	ensure_states(
		[
			("Draft", "Inverse"),
			("Pending Discount Approval", "Warning"),
			("Approved", "Success"),
			("Rejected", "Danger"),
			("Cancelled", "Inverse"),
		]
	)
	ensure_actions(["Submit", "Request Discount Approval", "Approve", "Reject", "Revise", "Cancel"])
	needs = f"{HML} and doc.hml_needs_discount_approval"
	within = f"({NOT_HML}) or not doc.hml_needs_discount_approval"
	upsert_workflow(
		"HML Quotation Approval",
		"Quotation",
		states=[
			("Draft", 0, "Sales User", None, None),
			("Pending Discount Approval", 0, "HML Sales Manager", None, None),
			("Rejected", 0, "Sales User", None, None),
			("Approved", 1, "Sales Manager", None, None),
			("Cancelled", 2, "Sales Manager", None, None),
		],
		transitions=[
			("Draft", "Submit", "Approved", "Sales User", within, 1),
			("Draft", "Request Discount Approval", "Pending Discount Approval", "Sales User", needs, 1),
			("Pending Discount Approval", "Approve", "Approved", "HML Sales Manager", None, 0),
			("Pending Discount Approval", "Approve", "Approved", "HML Sales Director", None, 0),
			("Pending Discount Approval", "Reject", "Rejected", "HML Sales Manager", None, 0),
			("Pending Discount Approval", "Reject", "Rejected", "HML Sales Director", None, 0),
			("Rejected", "Revise", "Draft", "Sales User", None, 1),
			("Approved", "Cancel", "Cancelled", "Sales Manager", None, 1),
		],
	)


def make_notifications():
	upsert_notification(
		"HML Delivery Dispatched",
		{
			"document_type": "Delivery Note",
			"event": "Submit",
			"channel": "Email",
			"condition": f'{HML} and not doc.is_return and not doc.is_internal_customer',
			"subject": "Your order {{ doc.items[0].against_sales_order or '' }} has been dispatched - {{ doc.name }}",
			"message": DISPATCH_MESSAGE,
			"recipients": [{"receiver_by_document_field": "contact_email"}],
			"attach_print": 1,
		},
	)


DISPATCH_MESSAGE = """<p>Dear {{ doc.contact_display or doc.customer_name }},</p>
<p>Your goods have left our {{ "Delhi" if doc.branch == "DC Delhi" else "Mumbai" }} warehouse.</p>
<table border="1" cellpadding="4" style="border-collapse:collapse">
<tr><th>Item</th><th>Qty</th><th>Sales Order</th></tr>
{% for row in doc.items %}<tr><td>{{ row.item_name }}</td><td>{{ row.qty }} {{ row.uom }}</td><td>{{ row.against_sales_order }}</td></tr>{% endfor %}
</table>
{% if doc.hml_has_deviation %}<p><b>Note:</b> {{ doc.hml_deviation_notes }}</p>{% endif %}
<p>Transporter: {{ doc.transporter_name or "Own vehicle" }} {{ doc.vehicle_no or "" }}<br>
Delivery Note {{ doc.name }} is attached.</p>
<p>Horizon Manufacturing Ltd</p>"""


def upsert_notification(name, values):
	if frappe.db.exists("Notification", name):
		doc = frappe.get_doc("Notification", name)
		doc.recipients = []
	else:
		doc = frappe.new_doc("Notification")
		doc.name = name
		doc.__newname = name
	recipients = values.pop("recipients", [])
	doc.update(values)
	doc.module = "Horizon ERP"
	doc.is_standard = 0
	doc.enabled = 1
	for r in recipients:
		doc.append("recipients", r)
	if doc.is_new():
		doc.insert(ignore_permissions=True, set_name=name)
	else:
		doc.save(ignore_permissions=True)


def make_all():
	make_quotation_workflow()
	make_notifications()
