import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class ItemDemandHistory(Document):
	def validate(self):
		try:
			self.period_start = getdate(f"{self.period}-01")
		except Exception:
			frappe.throw("Period must be YYYY-MM, e.g. 2026-01")
