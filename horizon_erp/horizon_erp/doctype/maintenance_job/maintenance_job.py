"""Maintenance Job: planned or breakdown maintenance on an asset.

On submit the cost is booked to the maintenance expense account with the
asset's cost center and location, so maintenance cost per asset and the
"maintenance as % of asset value" ratio come straight from the books.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MaintenanceJob(Document):
	def validate(self):
		self.total_cost = flt(self.labour_cost) + flt(self.parts_cost)
		if self.total_cost <= 0:
			frappe.throw(_("Enter the labour or parts cost."))

	def on_submit(self):
		asset = frappe.db.get_value("Asset", self.asset, ["cost_center", "branch"], as_dict=True)
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": self.company,
				"posting_date": self.job_date,
				"voucher_type": "Journal Entry",
				"title": f"Maintenance {self.asset_name}",
				"user_remark": f"{self.maintenance_type} maintenance {self.name} on {self.asset}: {self.description}",
				"accounts": [
					{
						"account": self.expense_account,
						"debit_in_account_currency": self.total_cost,
						"cost_center": asset.cost_center,
						"branch": asset.get("branch"),
					},
					{
						"account": self.payment_account,
						"credit_in_account_currency": self.total_cost,
						"cost_center": asset.cost_center,
						"branch": asset.get("branch"),
					},
				],
				"cheque_no": self.name,
				"cheque_date": self.job_date,
			}
		)
		je.flags.ignore_permissions = True
		je.insert()
		je.submit()
		self.db_set("journal_entry", je.name)

	def on_cancel(self):
		if self.journal_entry:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			if je.docstatus == 1:
				je.flags.ignore_permissions = True
				je.cancel()
