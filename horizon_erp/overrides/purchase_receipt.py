"""Purchase Receipt class override (no other app on this site overrides it).

1. Branch transfers between our own GSTINs arrive as a Purchase Receipt from
   the internal supplier. The goods were inspected when first received at
   Mumbai, so re-inspection is skipped for internal transfers only.
2. Partial lot rejection. ERPNext's "Stop if QI rejected" setting is global
   (it also guards the Leelas company) and blocks any receipt whose QI is
   Rejected. For Horizon, a failed QI is allowed through when the failed
   quantity has been moved to the Rejected warehouse on that line, because
   the bad goods are then segregated and returned automatically.
Every other receipt still goes through ERPNext's standard QI gate.
"""

import frappe
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt
from frappe.utils import flt

from horizon_erp.constants import is_hml


class HMLPurchaseReceipt(PurchaseReceipt):
	def validate_inspection(self):
		if self.get("is_internal_supplier"):
			return
		return super().validate_inspection()

	def validate_qi_rejection(self, row):
		if is_hml(self) and row.quality_inspection and flt(row.rejected_qty) > 0:
			rejected = frappe.db.get_value("Quality Inspection", row.quality_inspection, "hml_rejected_qty")
			if flt(rejected) and abs(flt(rejected) - flt(row.rejected_qty)) < 0.0001 and row.rejected_warehouse:
				return
		return super().validate_qi_rejection(row)
