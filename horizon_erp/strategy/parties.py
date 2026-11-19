"""Customer-supplier overlap (ABC Corp): net position and contra settlement.

ABC Corp is kept as two masters (Customer + Supplier) joined by a standard
Party Link - GST, credit control and approvals stay correct on each side.
Settlement is an explicit, approved Journal Entry ("contra"), never an
automatic netting, so both ledgers keep a full audit trail.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from horizon_erp.constants import COMPANY, acc, cc


def linked_parties(company=COMPANY):
	rows = []
	for link in frappe.get_all("Party Link", fields=["primary_role", "primary_party", "secondary_role", "secondary_party"]):
		customer = link.primary_party if link.primary_role == "Customer" else link.secondary_party
		supplier = link.secondary_party if link.secondary_role == "Supplier" else link.primary_party
		receivable = flt(
			frappe.db.sql(
				"select sum(debit - credit) from `tabGL Entry` where company = %s and party_type = 'Customer' and party = %s and is_cancelled = 0",
				(company, customer),
			)[0][0]
		)
		payable = flt(
			frappe.db.sql(
				"select sum(credit - debit) from `tabGL Entry` where company = %s and party_type = 'Supplier' and party = %s and is_cancelled = 0",
				(company, supplier),
			)[0][0]
		)
		rows.append(frappe._dict(customer=customer, supplier=supplier, receivable=receivable, payable=payable))
	return rows


@frappe.whitelist()
def create_contra_entry(customer, supplier, amount, posting_date=None, remark=None):
	"""Offset `amount` of what we owe the supplier against what the customer owes us."""
	frappe.has_permission("Journal Entry", "create", throw=True)
	amount = flt(amount)
	pos = next((r for r in linked_parties() if r.customer == customer and r.supplier == supplier), None)
	if not pos:
		frappe.throw(_("{0} and {1} are not linked (Party Link).").format(customer, supplier))
	limit = min(pos.receivable, pos.payable)
	if amount <= 0 or amount > limit + 0.01:
		frappe.throw(_("Contra amount must be between 0 and {0} (smaller of receivable and payable).").format(limit))
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Contra Entry",
			"company": COMPANY,
			"posting_date": posting_date or nowdate(),
			"user_remark": remark or _("Net settlement agreed with {0}: payable set off against receivable").format(
				frappe.db.get_value("Customer", customer, "customer_name")
			),
			"accounts": [
				{"account": acc("Creditors"), "party_type": "Supplier", "party": supplier, "debit_in_account_currency": amount, "cost_center": cc("Admin")},
				{"account": acc("Debtors"), "party_type": "Customer", "party": customer, "credit_in_account_currency": amount, "cost_center": cc("Admin")},
			],
		}
	)
	je.insert()
	return je.name
