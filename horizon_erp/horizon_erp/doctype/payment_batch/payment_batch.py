"""Payment Batch: bulk supplier payments with amount-based approval.

Workflow "HML Payment Batch Approval": up to Rs 5 L an Accounts Manager
approves, above that the Finance Director. On approval (submit) one Payment
Entry is posted per invoice line and a bank bulk-transfer CSV (NEFT/RTGS
lines) is attached; cheque lines are counted for the cheque print run.
"""

import csv
import io

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

APPROVAL_LIMIT = 500000


class PaymentBatch(Document):
	def validate(self):
		for row in self.items:
			inv = frappe.db.get_value(
				"Purchase Invoice", row.purchase_invoice, ["supplier", "outstanding_amount", "due_date", "docstatus", "company"], as_dict=True
			)
			if not inv or inv.docstatus != 1 or inv.company != self.company:
				frappe.throw(_("Row {0}: {1} is not a submitted invoice of {2}.").format(row.idx, row.purchase_invoice, self.company))
			row.supplier = inv.supplier
			row.outstanding = inv.outstanding_amount
			row.due_date = inv.due_date
			if flt(row.amount) > flt(inv.outstanding_amount) + 0.01:
				frappe.throw(_("Row {0}: amount exceeds outstanding {1}.").format(row.idx, inv.outstanding_amount))
			if row.mode != "Cheque" and not row.beneficiary_account:
				bank = frappe.db.get_value("Bank Account", {"party_type": "Supplier", "party": row.supplier}, ["bank_account_no", "branch_code"], as_dict=True)
				if bank:
					row.beneficiary_account, row.ifsc = bank.bank_account_no, bank.branch_code
		self.total_amount = sum(flt(r.amount) for r in self.items)
		self.approval_level = "Finance Director (above Rs 5 L)" if self.total_amount > APPROVAL_LIMIT else "Accounts Manager (up to Rs 5 L)"
		self.title = f"{len(self.items)} payments - {frappe.format(self.total_amount, 'Currency')}"

	def on_submit(self):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		paid_from = frappe.db.get_value("Bank Account", self.bank_account, "account")
		for row in self.items:
			pe = get_payment_entry("Purchase Invoice", row.purchase_invoice, party_amount=row.amount, bank_account=paid_from)
			pe.posting_date = self.posting_date
			pe.paid_from = paid_from
			pe.paid_amount = pe.received_amount = row.amount
			pe.references[0].allocated_amount = row.amount
			pe.mode_of_payment = "Cheque" if row.mode == "Cheque" else "Wire Transfer"
			pe.reference_no = row.cheque_no or f"{self.name}-{row.idx}"
			pe.reference_date = self.posting_date
			pe.remarks = f"Payment batch {self.name}"
			pe.flags.ignore_permissions = True
			pe.insert()
			pe.submit()
			row.db_set("payment_entry", pe.name)
		self.attach_transfer_file()

	def attach_transfer_file(self):
		buf = io.StringIO()
		w = csv.writer(buf)
		w.writerow(["Transaction Type", "Beneficiary Name", "Beneficiary Account No", "IFSC", "Amount", "Value Date", "Customer Reference", "Remarks"])
		cheques = 0
		for row in self.items:
			if row.mode == "Cheque":
				cheques += 1
				continue
			w.writerow([
				row.mode, frappe.db.get_value("Supplier", row.supplier, "supplier_name"), row.beneficiary_account or "",
				row.ifsc or "", f"{flt(row.amount):.2f}", frappe.utils.formatdate(self.posting_date, "dd/MM/yyyy"),
				row.payment_entry, f"Inv {frappe.db.get_value('Purchase Invoice', row.purchase_invoice, 'bill_no') or row.purchase_invoice}",
			])
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{self.name}-bank-transfer.csv",
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"content": buf.getvalue(),
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		self.db_set({"transfer_file": f.file_url, "cheque_count": cheques})
