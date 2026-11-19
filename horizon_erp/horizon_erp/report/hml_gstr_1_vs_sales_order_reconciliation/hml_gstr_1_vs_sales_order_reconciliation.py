"""HML GSTR-1 vs Sales Order Reconciliation.

Quantity reported in GSTR-1 (= submitted, non-return Sales Invoices in the
period) against the Sales Order quantity and the delivered quantity per SO
line. Anything not "Matched" is a question for Sales / Accounts before the
return is filed: invoiced more than ordered, invoiced without delivery (only
legitimate under an approved bill-and-hold decision), or invoices with no
Sales Order at all.
"""

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.constants import COMPANY


def execute(filters=None):
	filters = frappe._dict(filters or {})
	f = {"company": COMPANY, "from_date": filters.from_date or "2026-04-01", "to_date": filters.to_date or "2027-03-31"}
	inv = frappe.db.sql(
		"""select sii.so_detail, sii.sales_order, sii.item_code, sum(sii.stock_qty) qty, sum(sii.base_net_amount) value,
			group_concat(distinct si.name) invoices
		from `tabSales Invoice Item` sii join `tabSales Invoice` si on si.name = sii.parent
		where si.company = %(company)s and si.docstatus = 1 and si.is_return = 0 and ifnull(si.is_internal_customer, 0) = 0
			and si.posting_date between %(from_date)s and %(to_date)s
		group by sii.so_detail, sii.sales_order, sii.item_code""",
		f, as_dict=True)
	data = []
	for r in inv:
		if r.so_detail:
			so = frappe.db.get_value("Sales Order Item", r.so_detail, ["qty", "delivered_qty", "stock_uom", "parent"], as_dict=True)
			diff = flt(r.qty) - flt(so.qty)
			if abs(diff) < 0.0001 or flt(r.qty) <= flt(so.qty):
				status = "Matched" if flt(r.qty) <= flt(so.delivered_qty) + 0.0001 else "Invoiced before delivery"
				if status == "Matched" and flt(r.qty) < flt(so.qty):
					status = "Matched (partial order)"
			else:
				status = "Invoiced more than ordered"
			data.append({"sales_order": r.sales_order, "item_code": r.item_code, "so_qty": so.qty, "delivered_qty": so.delivered_qty,
				"gstr1_qty": r.qty, "difference": flt(r.qty) - flt(so.delivered_qty), "value": r.value, "invoices": r.invoices, "status": status})
		else:
			data.append({"sales_order": None, "item_code": r.item_code, "gstr1_qty": r.qty, "value": r.value, "invoices": r.invoices,
				"status": "No Sales Order" if not frappe.db.get_value("Item", r.item_code, "is_fixed_asset") else "Asset sale (no SO needed)"})
	cols = [
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 140},
		{"label": _("SO Qty"), "fieldname": "so_qty", "fieldtype": "Float", "width": 80},
		{"label": _("Delivered"), "fieldname": "delivered_qty", "fieldtype": "Float", "width": 85},
		{"label": _("GSTR-1 Qty (invoiced)"), "fieldname": "gstr1_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Invoiced - Delivered"), "fieldname": "difference", "fieldtype": "Float", "width": 130},
		{"label": _("Taxable Value"), "fieldname": "value", "fieldtype": "Currency", "width": 120},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 190},
		{"label": _("Invoices"), "fieldname": "invoices", "fieldtype": "Data", "width": 220},
	]
	summary = [
		{"label": _("Lines"), "value": len(data), "indicator": "Blue"},
		{"label": _("Exceptions"), "value": len([d for d in data if not d["status"].startswith(("Matched", "Asset"))]), "indicator": "Red"},
	]
	return cols, data, None, None, summary
