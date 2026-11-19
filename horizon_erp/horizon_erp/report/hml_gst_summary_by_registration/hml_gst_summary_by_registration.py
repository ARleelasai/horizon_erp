"""HML GST Summary by Registration (GSTR-1 / GSTR-3B style totals per GSTIN).

Outward: Sales Invoices by our GSTIN (Mumbai 27 / Delhi 07) - taxable value,
CGST, SGST, IGST (inter-branch transfers shown separately). Inward:
Purchase Invoices - ITC by tax type, reverse-charge liability. Net cash
liability = output - ITC (before set-off rules). The statutory returns
themselves come from India Compliance (GSTR-1 Beta, GSTR-3B).
"""

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.constants import COMPANY


def _tax_split(doctype, child, filters):
	return frappe.db.sql(
		f"""
		select d.company_gstin gstin, ifnull(d.is_internal_{'customer' if doctype == 'Sales Invoice' else 'supplier'}, 0) internal,
			ifnull(d.is_reverse_charge, 0) rcm, count(distinct d.name) docs,
			sum(case when t.account_head like '%%CGST%%' then t.base_tax_amount_after_discount_amount else 0 end) cgst,
			sum(case when t.account_head like '%%SGST%%' then t.base_tax_amount_after_discount_amount else 0 end) sgst,
			sum(case when t.account_head like '%%IGST%%' then t.base_tax_amount_after_discount_amount else 0 end) igst
		from `tab{doctype}` d left join `tab{child}` t on t.parent = d.name
		where d.company = %(company)s and d.docstatus = 1 and d.posting_date between %(from_date)s and %(to_date)s
		group by gstin, internal, rcm""",
		filters,
		as_dict=True,
	)


def _taxable(doctype, filters, gstin, internal, rcm):
	field = "is_internal_customer" if doctype == "Sales Invoice" else "is_internal_supplier"
	return flt(frappe.db.sql(
		f"""select sum(base_net_total) from `tab{doctype}` where company = %(company)s and docstatus = 1
		and posting_date between %(from_date)s and %(to_date)s and company_gstin = %(gstin)s
		and ifnull({field}, 0) = %(internal)s and ifnull(is_reverse_charge, 0) = %(rcm)s""",
		{**filters, "gstin": gstin, "internal": internal, "rcm": rcm})[0][0])


def execute(filters=None):
	filters = frappe._dict(filters or {})
	f = {"company": COMPANY, "from_date": filters.from_date or "2026-04-01", "to_date": filters.to_date or "2027-03-31"}
	data = []
	for doctype, child, direction in (("Sales Invoice", "Sales Taxes and Charges", "Outward"), ("Purchase Invoice", "Purchase Taxes and Charges", "Inward")):
		for r in _tax_split(doctype, child, f):
			kind = "Branch transfer" if r.internal else ("Reverse charge" if r.rcm else ("Supplies" if direction == "Outward" else "Purchases (ITC)"))
			data.append(
				{
					"gstin": r.gstin, "branch": "Mumbai HQ" if (r.gstin or "").startswith("27") else ("Delhi DC" if (r.gstin or "").startswith("07") else "-"),
					"direction": direction, "kind": kind, "documents": r.docs,
					"taxable": _taxable(doctype, f, r.gstin, r.internal, r.rcm),
					"cgst": flt(r.cgst), "sgst": flt(r.sgst), "igst": flt(r.igst),
					"total_tax": flt(r.cgst) + flt(r.sgst) + flt(r.igst),
				}
			)
	net = {}
	for d in data:
		sign = 1 if d["direction"] == "Outward" else -1
		net[d["gstin"]] = net.get(d["gstin"], 0) + sign * d["total_tax"]
	cols = [
		{"label": _("Our GSTIN"), "fieldname": "gstin", "fieldtype": "Data", "width": 150},
		{"label": _("Location"), "fieldname": "branch", "fieldtype": "Data", "width": 95},
		{"label": _("Direction"), "fieldname": "direction", "fieldtype": "Data", "width": 85},
		{"label": _("Type"), "fieldname": "kind", "fieldtype": "Data", "width": 130},
		{"label": _("Documents"), "fieldname": "documents", "fieldtype": "Int", "width": 85},
		{"label": _("Taxable Value"), "fieldname": "taxable", "fieldtype": "Currency", "width": 130},
		{"label": _("CGST"), "fieldname": "cgst", "fieldtype": "Currency", "width": 110},
		{"label": _("SGST"), "fieldname": "sgst", "fieldtype": "Currency", "width": 110},
		{"label": _("IGST"), "fieldname": "igst", "fieldtype": "Currency", "width": 110},
		{"label": _("Total Tax"), "fieldname": "total_tax", "fieldtype": "Currency", "width": 120},
	]
	summary = [{"label": _("Net GST {0}").format(g), "value": v, "datatype": "Currency", "indicator": "Red" if v > 0 else "Green"} for g, v in net.items() if g]
	return cols, data, None, None, summary
