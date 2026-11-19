"""Monthly bank reconciliation sign-off and period lock.

Validate: computes GL balance at period end, difference to the statement,
the part explained by open bank transactions that carry an exception
classification (post-dated cheque, clearing delay, timing difference ...),
and refuses sign-off while any difference is unexplained or any open item is
unclassified. Submit locks the period (horizon_erp.accounts.bank.validate_bank_lock).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from horizon_erp.accounts.bank import open_bank_transactions


class BankReconciliationLock(Document):
	def validate(self):
		from erpnext.accounts.utils import get_balance_on

		self.gl_balance = flt(get_balance_on(self.account, self.period_end))
		self.difference = flt(self.statement_balance) - self.gl_balance
		items = open_bank_transactions(self.bank_account, self.period_end)
		self.unreconciled_count = len(items)
		self.unclassified_count = len([i for i in items if not i.hml_exception_type])
		# open bank-side items explain statement vs book: deposits not in books (+), withdrawals not in books (-)
		self.explained_difference = sum(flt(i.unallocated_amount) * (1 if flt(i.deposit) else -1) for i in items)
		self.unexplained = round(self.difference - self.explained_difference, 2)

	def before_submit(self):
		if self.unclassified_count:
			frappe.throw(_("{0} open bank transactions have no exception classification. Match them or classify them before sign-off.").format(self.unclassified_count))
		if abs(flt(self.unexplained)) > 1:
			frappe.throw(_("Unexplained difference of {0}. Reconcile before signing off.").format(frappe.format(self.unexplained, "Currency")))
		self.signed_off_by = frappe.session.user
		frappe.db.set_value("Bank Account", self.bank_account, "hml_reconciled_upto", self.period_end)

	def on_cancel(self):
		prev = frappe.db.get_value(
			"Bank Reconciliation Lock",
			{"bank_account": self.bank_account, "docstatus": 1, "name": ("!=", self.name)},
			"max(period_end)",
		)
		frappe.db.set_value("Bank Account", self.bank_account, "hml_reconciled_upto", prev)
