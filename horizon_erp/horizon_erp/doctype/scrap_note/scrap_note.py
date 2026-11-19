"""Scrap Note: write off obsolete stock found by the obsolescence report.

On submit, "Scrap" lines are moved out with a Material Issue whose expense
account is Scrap and Obsolescence Loss (so the write-off is visible in the
P&L, not buried in stock adjustment). Clearance / supplier-return lines are
only recorded here for follow-up.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from horizon_erp.constants import acc, cc


class ScrapNote(Document):
	def validate(self):
		for row in self.items:
			bin_ = frappe.db.get_value("Bin", {"item_code": row.item_code, "warehouse": row.warehouse}, ["actual_qty", "valuation_rate"], as_dict=True)
			if not bin_ or flt(bin_.actual_qty) < flt(row.qty):
				frappe.throw(_("Row {0}: only {1} of {2} in {3}.").format(row.idx, bin_.actual_qty if bin_ else 0, row.item_code, row.warehouse))
			row.valuation_rate = bin_.valuation_rate
			row.value = flt(row.qty) * flt(bin_.valuation_rate)
		self.total_value = sum(flt(r.value) for r in self.items)
		self.title = self.title or f"Scrap {len(self.items)} items - {frappe.format(self.total_value, 'Currency')}"

	def on_submit(self):
		lines = [r for r in self.items if r.disposition == "Scrap"]
		if not lines:
			return
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Issue",
				"company": self.company,
				"posting_date": self.posting_date,
				"set_posting_time": 1,
				"remarks": f"Scrap Note {self.name}: {self.reason}",
				"items": [
					{"item_code": r.item_code, "qty": r.qty, "s_warehouse": r.warehouse,
						"expense_account": acc("Scrap and Obsolescence Loss"), "cost_center": cc("Admin")}
					for r in lines
				],
			}
		)
		se.flags.ignore_permissions = True
		se.insert()
		se.submit()
		self.db_set("stock_entry", se.name)

	def on_cancel(self):
		if self.stock_entry:
			se = frappe.get_doc("Stock Entry", self.stock_entry)
			if se.docstatus == 1:
				se.flags.ignore_permissions = True
				se.cancel()
