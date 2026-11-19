"""HML Bank Reconciliation Statement with aging.

Header (summary): bank statement balance (opening + transactions imported up
to the date), GL balance, variance. Rows: every item that explains the
variance - bank entries not yet in the books, and book entries not yet
cleared by the bank - with age in days; older than 30 days is flagged.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

from horizon_erp.accounts.bank import open_bank_transactions


def execute(filters=None):
	filters = frappe._dict(filters or {})
	bank = filters.bank_account or frappe.db.get_value("Bank Account", {"company": "Horizon Manufacturing Ltd", "is_company_account": 1})
	on = getdate(filters.as_on_date or nowdate())
	account = frappe.db.get_value("Bank Account", bank, "account")
	from erpnext.accounts.utils import get_balance_on

	gl = flt(get_balance_on(account, on))
	opening = flt(frappe.db.get_value("Bank Account", bank, "hml_statement_opening") or 0) if frappe.get_meta("Bank Account").has_field("hml_statement_opening") else 0
	stmt = opening + flt(frappe.db.sql(
		"select sum(deposit - withdrawal) from `tabBank Transaction` where bank_account = %s and docstatus = 1 and date <= %s", (bank, on))[0][0])
	data = []
	for bt in open_bank_transactions(bank, on):
		amt = flt(bt.unallocated_amount) * (1 if flt(bt.deposit) else -1)
		data.append({"side": "Bank, not in books", "date": bt.date, "reference": bt.name, "description": bt.description,
			"amount": amt, "age": date_diff(on, bt.date), "exception": bt.hml_exception_type})
	for v in frappe.db.sql(
		"""select 'Payment Entry' dt, name, posting_date, reference_no, if(paid_to = %(acc)s, paid_amount, -paid_amount) amt, party
		from `tabPayment Entry` where docstatus = 1 and (paid_to = %(acc)s or paid_from = %(acc)s)
			and posting_date <= %(on)s and (clearance_date is null or clearance_date > %(on)s)
		union all
		select 'Journal Entry', je.name, je.posting_date, je.cheque_no, jea.debit - jea.credit, jea.party
		from `tabJournal Entry` je join `tabJournal Entry Account` jea on jea.parent = je.name
		where je.docstatus = 1 and jea.account = %(acc)s and je.posting_date <= %(on)s
			and (je.clearance_date is null or je.clearance_date > %(on)s)""",
		{"acc": account, "on": on}, as_dict=True,
	):
		data.append({"side": "Books, not cleared by bank", "date": v.posting_date, "reference": v.name, "description": f"{v.dt} {v.reference_no or ''} {v.party or ''}",
			"amount": flt(v.amt), "age": date_diff(on, v.posting_date), "exception": None})
	for d in data:
		d["flag"] = 1 if d["age"] > 30 else 0
	data.sort(key=lambda d: -d["age"])
	cols = [
		{"label": _("Side"), "fieldname": "side", "fieldtype": "Data", "width": 190},
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 95},
		{"label": _("Reference"), "fieldname": "reference", "fieldtype": "Data", "width": 170},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 260},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Age (days)"), "fieldname": "age", "fieldtype": "Int", "width": 85},
		{"label": _("> 30 days"), "fieldname": "flag", "fieldtype": "Check", "width": 75},
		{"label": _("Exception"), "fieldname": "exception", "fieldtype": "Data", "width": 150},
	]
	summary = [
		{"label": _("Bank balance (statement)"), "value": stmt, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("GL balance"), "value": gl, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Variance"), "value": stmt - gl, "datatype": "Currency", "indicator": "Red" if abs(stmt - gl) > 1 else "Green"},
		{"label": _("Unmatched > 30 days"), "value": len([d for d in data if d["flag"]]), "indicator": "Red"},
	]
	return cols, data, None, None, summary
