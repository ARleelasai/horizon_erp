"""Purchase Receipt class override (no other app on this site overrides it).

Branch transfers between our own GSTINs arrive as a Purchase Receipt from the
internal supplier. The goods were already inspected when they were first
received at Mumbai, so re-inspection is skipped for internal transfers only.
Every external receipt still goes through ERPNext's Quality Inspection gate.
"""

from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt


class HMLPurchaseReceipt(PurchaseReceipt):
	def validate_inspection(self):
		if self.get("is_internal_supplier"):
			return
		return super().validate_inspection()
