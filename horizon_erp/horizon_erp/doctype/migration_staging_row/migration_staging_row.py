import frappe
from frappe.model.document import Document


class MigrationStagingRow(Document):
	def validate(self):
		if self.status in ("Approved for Import", "Rejected") and not self.reviewed_by and self.issue not in (None, "", "None"):
			self.reviewed_by = frappe.session.user
