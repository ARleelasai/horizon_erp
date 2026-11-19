"""HML Net Party Position - entities that are both customer and supplier.

For every Party Link: what they owe us (receivable), what we owe them
(payable), the net, and the amount that can be set off. Also lists
customers and suppliers that share a PAN / GSTIN but are not linked yet.
"""

import frappe
from frappe import _

from horizon_erp.strategy.parties import linked_parties


def execute(filters=None):
	data = []
	for p in linked_parties():
		net = p.receivable - p.payable
		data.append(
			{
				"customer": p.customer, "customer_name": frappe.db.get_value("Customer", p.customer, "customer_name"),
				"supplier": p.supplier, "receivable": p.receivable, "payable": p.payable, "net": net,
				"position": "They owe us" if net > 0 else ("We owe them" if net < 0 else "Square"),
				"settle_off": max(min(p.receivable, p.payable), 0), "linked": 1,
			}
		)
	linked_pairs = {(d["customer"], d["supplier"]) for d in data}
	for r in frappe.db.sql(
		"""select c.name customer, c.customer_name, s.name supplier from `tabCustomer` c join `tabSupplier` s
		on ((c.pan = s.pan and ifnull(c.pan, '') != '') or (c.gstin = s.gstin and ifnull(c.gstin, '') != ''))
		where ifnull(c.is_internal_customer, 0) = 0 and ifnull(s.is_internal_supplier, 0) = 0""",
		as_dict=True,
	):
		if (r.customer, r.supplier) not in linked_pairs:
			data.append({"customer": r.customer, "customer_name": r.customer_name, "supplier": r.supplier, "position": "Same PAN - not linked", "linked": 0})
	cols = [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 140},
		{"label": _("Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 170},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 140},
		{"label": _("Receivable (they owe us)"), "fieldname": "receivable", "fieldtype": "Currency", "width": 150},
		{"label": _("Payable (we owe them)"), "fieldname": "payable", "fieldtype": "Currency", "width": 150},
		{"label": _("Net"), "fieldname": "net", "fieldtype": "Currency", "width": 130},
		{"label": _("Position"), "fieldname": "position", "fieldtype": "Data", "width": 160},
		{"label": _("Can Be Set Off"), "fieldname": "settle_off", "fieldtype": "Currency", "width": 130},
		{"label": _("Party Link"), "fieldname": "linked", "fieldtype": "Check", "width": 80},
	]
	return cols, data
