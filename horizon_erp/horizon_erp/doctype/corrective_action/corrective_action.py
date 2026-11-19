import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class CorrectiveAction(Document):
	def validate(self):
		if self.status in ("Completed", "Verified") and not self.completed_on:
			self.completed_on = nowdate()
		if self.status == "Verified":
			self.verified_by = self.verified_by or frappe.session.user
			if self.verified_by == self.owner_user and "System Manager" not in frappe.get_roles():
				frappe.throw(_("Effectiveness must be verified by someone other than the action owner."))
		self.is_overdue = 1 if self.status in ("Open", "In Progress") and getdate(self.due_date) < getdate(nowdate()) else 0

	def on_update(self):
		if self.production_audit and self.status in ("Completed", "Verified"):
			from horizon_erp.manufacturing.audit import release_audit_hold

			release_audit_hold(self.production_audit)


def mark_overdue():
	"""Daily: refresh the Overdue flag."""
	frappe.db.sql(
		"""update `tabCorrective Action` set is_overdue = if(status in ('Open', 'In Progress') and due_date < %s, 1, 0)""",
		nowdate(),
	)
