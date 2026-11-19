"""Budget Overage Approval.

A document stopped by an ERPNext budget (action "Stop") stays in draft; the
requester raises this approval. When the Finance Director approves (submit
via workflow), the held document is submitted in the Finance Director's
session with ERPNext's "exception budget approver role" set to HML Finance
Director, so the budget stop becomes a warning for that user only - the
overage goes through, and this record is the audit log.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from horizon_erp.accounts.budget import budget_position


class BudgetOverageApproval(Document):
	def validate(self):
		ref = frappe.get_doc(self.reference_doctype, self.reference_name)
		if ref.docstatus != 0:
			frappe.throw(_("{0} is not a draft.").format(self.reference_name))
		pos = budget_position(self.company, self.cost_center, self.account, ref)
		self.annual_budget = pos.budget
		self.actual_to_date = pos.actual
		self.request_amount = pos.this_document
		self.overage = max(pos.actual + pos.this_document - pos.budget, 0)

	def on_submit(self):
		if self.get("workflow_state") == "Rejected":
			return
		if "HML Finance Director" not in frappe.get_roles():
			frappe.throw(_("Only the Finance Director can approve a budget overage."))
		self.db_set({"decision": "Approved", "decided_by": frappe.session.user})
		ref = frappe.get_doc(self.reference_doctype, self.reference_name)
		ref.add_comment("Comment", _("Budget overage approved via {0} by {1}.").format(self.name, frappe.session.user))
		ref.flags.ignore_permissions = True
		# ERPNext reads the company's exception approver role only on the
		# PO / MR path; GL postings (JE, PI) need the flag set explicitly.
		saved = frappe.flags.exception_approver_role
		frappe.flags.exception_approver_role = "HML Finance Director"
		try:
			ref.submit()
		finally:
			frappe.flags.exception_approver_role = saved

	def on_update(self):
		if self.get("workflow_state") == "Rejected" and self.decision != "Rejected":
			self.db_set({"decision": "Rejected", "decided_by": frappe.session.user})
