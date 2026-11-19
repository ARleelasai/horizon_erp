"""Bank reconciliation helpers for Horizon.

auto_match(): matches unreconciled Bank Transactions to Payment Entries /
Journal Entries on the same bank GL account by
	1. reference number (cheque / UTR) and amount, then
	2. exact amount within +/- 3 days, only when exactly one candidate exists.
Anything ambiguous is left for the manual Bank Reconciliation Tool, so the
auto-matcher never guesses.

validate_bank_lock(): no Payment / Journal Entry on a bank account may be
posted on or before the last signed-off reconciliation (Bank Reconciliation Lock).
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

from horizon_erp.constants import COMPANY

DATE_WINDOW = 3


def open_bank_transactions(bank_account, upto=None):
	filters = {"bank_account": bank_account, "docstatus": 1, "unallocated_amount": (">", 0)}
	if upto:
		filters["date"] = ("<=", upto)
	return frappe.get_all(
		"Bank Transaction",
		filters=filters,
		fields=["name", "date", "deposit", "withdrawal", "unallocated_amount", "reference_number", "description",
			"hml_exception_type", "hml_exception_note"],
		order_by="date",
	)


def _candidates(account, amount, is_deposit, date, reference=None):
	"""Unreconciled vouchers hitting the bank account for this amount."""
	pe_field = "paid_to" if is_deposit else "paid_from"
	rows = frappe.db.sql(
		f"""select 'Payment Entry' doctype, name, posting_date, reference_no from `tabPayment Entry`
		where docstatus = 1 and {pe_field} = %(account)s and ifnull(clearance_date, '') = ''
			and abs(paid_amount - %(amount)s) < 0.01
		union all
		select 'Journal Entry', je.name, je.posting_date, je.cheque_no from `tabJournal Entry` je
		join `tabJournal Entry Account` jea on jea.parent = je.name
		where je.docstatus = 1 and jea.account = %(account)s and ifnull(je.clearance_date, '') = ''
			and abs(jea.{'debit' if is_deposit else 'credit'} - %(amount)s) < 0.01""",
		{"account": account, "amount": amount},
		as_dict=True,
	)
	if reference:
		by_ref = [r for r in rows if r.reference_no and r.reference_no.strip().lower() == reference.strip().lower()]
		if by_ref:
			return by_ref, "reference"
	near = [r for r in rows if abs((getdate(r.posting_date) - getdate(date)).days) <= DATE_WINDOW]
	return near, "amount+date"


@frappe.whitelist()
def auto_match(bank_account, upto=None):
	from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import reconcile_vouchers
	import json

	frappe.has_permission("Bank Transaction", "write", throw=True)
	account = frappe.db.get_value("Bank Account", bank_account, "account")
	matched, skipped = [], []
	for bt in open_bank_transactions(bank_account, upto):
		amount = flt(bt.deposit) or flt(bt.withdrawal)
		cands, how = _candidates(account, amount, bool(flt(bt.deposit)), bt.date, bt.reference_number)
		if len(cands) != 1:
			skipped.append({"bank_transaction": bt.name, "candidates": len(cands)})
			continue
		c = cands[0]
		reconcile_vouchers(
			bt.name,
			json.dumps([{"payment_doctype": c.doctype, "payment_name": c.name, "amount": amount}]),
		)
		frappe.db.set_value("Bank Transaction", bt.name, "hml_auto_matched", how)
		matched.append({"bank_transaction": bt.name, "voucher": c.name, "rule": how})
	return {"matched": matched, "left_for_manual": skipped}


def validate_bank_lock(doc, method=None):
	if doc.get("company") != COMPANY:
		return
	accounts = set()
	if doc.doctype == "Payment Entry":
		accounts = {doc.paid_from, doc.paid_to}
	elif doc.doctype == "Journal Entry":
		accounts = {r.account for r in doc.accounts}
	for bank in frappe.get_all(
		"Bank Account", filters={"account": ("in", [a for a in accounts if a]), "hml_reconciled_upto": ("is", "set")},
		fields=["name", "hml_reconciled_upto"],
	):
		if getdate(doc.posting_date) <= getdate(bank.hml_reconciled_upto):
			frappe.throw(
				_("{0} is reconciled and locked up to {1}. Post this entry in an open period.").format(
					bank.name, frappe.format(bank.hml_reconciled_upto, "Date")
				),
				title=_("Bank period locked"),
			)
