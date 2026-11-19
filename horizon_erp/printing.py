"""Jinja helpers for Horizon print formats (registered in hooks.jinja)."""

import frappe
from frappe.utils import add_days, cint, flt, getdate


def hml_customer_outstanding(customer, company):
	return flt(
		frappe.db.sql(
			"select sum(outstanding_amount) from `tabSales Invoice` where customer = %s and company = %s and docstatus = 1",
			(customer, company),
		)[0][0]
	)


def hml_payment_due_date(doc):
	"""Invoice date + credit days of the payment terms template (falls back to due_date)."""
	days = 0
	if doc.get("payment_terms_template"):
		days = max(
			[cint(t.credit_days) for t in frappe.get_all(
				"Payment Terms Template Detail", filters={"parent": doc.payment_terms_template}, fields=["credit_days"])] or [0]
		)
	return add_days(doc.posting_date, days) if days else getdate(doc.due_date or doc.posting_date)


def hml_total_discount_pct(doc):
	list_value = sum(flt(r.price_list_rate) * flt(r.qty) for r in doc.items)
	return round((1 - flt(doc.net_total) / list_value) * 100, 2) if list_value else 0


def hml_similar_in_stock(item_code, limit=3):
	"""Cross-sell hint: other sellable items of the same category with stock."""
	group = frappe.db.get_value("Item", item_code, "item_group")
	return frappe.db.sql(
		"""select i.item_code, i.item_name, sum(b.actual_qty - b.reserved_qty) qty
		from `tabItem` i join `tabBin` b on b.item_code = i.name
		join `tabWarehouse` w on w.name = b.warehouse and w.company = 'Horizon Manufacturing Ltd'
		where i.item_group = %s and i.name != %s and i.is_sales_item = 1 and i.disabled = 0
		group by i.item_code having qty > 0 order by qty desc limit %s""",
		(group, item_code, limit),
		as_dict=True,
	)


def hml_company_registration(company, gstin=None):
	addr = frappe.db.get_value(
		"Address", {"is_your_company_address": 1, "gstin": gstin} if gstin else {"is_your_company_address": 1},
		["address_line1", "address_line2", "city", "state", "pincode", "gstin", "gst_state_number"], as_dict=True,
	)
	pan = frappe.db.get_value("Company", company, "pan")
	return frappe._dict(address=addr, pan=pan)
