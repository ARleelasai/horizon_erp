"""Production Audit - daily shop-floor audit with escalation.

Workflow (HML Production Audit): Draft -> Submitted -> Reviewed -> Action Closed.
On submit with score < 70:
  * every HML Operations Head gets a bell notification + email immediately,
  * a Corrective Action is opened (owner: first Operations Head, due in 3 days),
  * the Work Order is put on audit hold: its Manufacture entry is blocked
    until the corrective action is Completed / Verified (manufacturing/audit.py).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, get_url_to_form, nowdate, strip_html

from horizon_erp.notify import notify

CRITICAL = 70
GOOD = 85


class ProductionAudit(Document):
	def validate(self):
		if self.audit_score is None or not 0 <= int(self.audit_score) <= 100:
			frappe.throw(_("Audit Score must be between 0 and 100."))
		self.score_band = (
			"Critical (< 70)" if self.audit_score < CRITICAL else ("Attention (70-84)" if self.audit_score < GOOD else "Good (85+)")
		)
		if self.audit_score < CRITICAL and not self.photo_1:
			frappe.throw(_("Photo evidence is mandatory when the audit score is below {0}.").format(CRITICAL))

	def on_submit(self):
		if self.audit_score < CRITICAL:
			self.escalate()

	def on_update_after_submit(self):
		state = self.get("workflow_state")
		if state == "Reviewed" and not self.reviewed_by:
			self.db_set("reviewed_by", frappe.session.user)
		if state == "Action Closed":
			if self.audit_score < CRITICAL:
				ca_status = frappe.db.get_value("Corrective Action", self.corrective_action, "status") if self.corrective_action else None
				if ca_status not in ("Completed", "Verified"):
					frappe.throw(_("Close the corrective action {0} before closing this audit.").format(self.corrective_action or ""))
			if not self.action_closed_on:
				self.db_set("action_closed_on", nowdate())
			from horizon_erp.manufacturing.audit import release_audit_hold

			release_audit_hold(self.name)

	def on_cancel(self):
		from horizon_erp.manufacturing.audit import release_audit_hold

		release_audit_hold(self.name, force=True)

	def escalate(self):
		heads = [
			u
			for u in frappe.get_all("Has Role", filters={"role": "HML Operations Head", "parenttype": "User"}, pluck="parent")
			if frappe.db.get_value("User", u, "enabled") and u != "Administrator"
		]
		if not self.corrective_action:
			ca = frappe.get_doc(
				{
					"doctype": "Corrective Action",
					"title": f"Audit {self.name}: score {self.audit_score} on {self.work_order}",
					"company": self.company,
					"source": "Production Audit",
					"production_audit": self.name,
					"work_order": self.work_order,
					"owner_user": heads[0] if heads else frappe.session.user,
					"due_date": add_days(nowdate(), 3),
					"problem": strip_html(self.findings or "")[:1000] or _("Audit score below 70"),
					"action_plan": _("<p>Contain: rework affected units before the Work Order can be completed.</p><p>Correct: fix the root cause found in the audit.</p>"),
				}
			).insert(ignore_permissions=True)
			self.db_set("corrective_action", ca.name)
		self.db_set("escalated", 1)
		frappe.db.set_value("Work Order", self.work_order, "hml_audit_hold", 1)
		notify(
			heads,
			subject=_("Production audit {0} scored {1} on {2} - Work Order on hold").format(self.name, self.audit_score, self.work_order),
			message=_(
				"<p>Audit <a href='{0}'>{1}</a> on Work Order {2} ({3}, line {4}) scored <b>{5}</b>.</p>"
				"<p>Findings: {6}</p><p>Corrective Action {7} is assigned and due in 3 days. "
				"The Work Order cannot be completed until it is closed.</p>"
			).format(
				get_url_to_form(self.doctype, self.name), self.name, self.work_order, self.production_item,
				self.production_line or "-", self.audit_score, strip_html(self.findings or "")[:500], self.corrective_action,
			),
			reference_doctype=self.doctype,
			reference_name=self.name,
		)


@frappe.whitelist()
def get_work_order_context(work_order):
	wo = frappe.db.get_value(
		"Work Order",
		work_order,
		["name", "production_item", "item_name", "qty", "produced_qty", "status", "hml_production_line", "sales_order",
			"planned_start_date", "hml_deadline", "hml_audit_hold"],
		as_dict=True,
	)
	if wo:
		wo.previous_audits = frappe.get_all(
			"Production Audit",
			filters={"work_order": work_order, "docstatus": 1},
			fields=["name", "audit_date", "audit_score"],
			order_by="audit_date desc",
			limit=5,
		)
	return wo
