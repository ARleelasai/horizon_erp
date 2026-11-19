"""HML Order Fulfilment Status: Ordered -> Delivered -> Invoiced per SO line.

Flags:
* Overdue: undelivered qty and delivery date more than OVERDUE_DAYS in the past.
* Partial: some but not all of the line delivered.
* Delivery risk: the promised date was earlier than the achievable estimate
  when the order was taken (Sales Order.hml_delivery_risk).
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

from horizon_erp.constants import COMPANY

OVERDUE_DAYS = 5


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.company or COMPANY
	as_on = getdate(filters.as_on_date or nowdate())
	data = get_data(filters, as_on)
	return get_columns(), data, None, get_chart(data), get_summary(data)


def get_data(filters, as_on):
	conditions = ["so.docstatus = 1", "so.company = %(company)s", "so.status not in ('Closed', 'On Hold')"]
	if filters.from_date:
		conditions.append("so.transaction_date >= %(from_date)s")
	if filters.to_date:
		conditions.append("so.transaction_date <= %(to_date)s")
	if filters.customer:
		conditions.append("so.customer = %(customer)s")
	if filters.branch:
		conditions.append("so.branch = %(branch)s")
	rows = frappe.db.sql(
		f"""
		select so.name as sales_order, so.customer, so.customer_name, so.branch,
			so.transaction_date, so.hml_delivery_risk as delivery_risk,
			soi.name as so_detail, soi.item_code, soi.item_name,
			ifnull(soi.delivery_date, so.delivery_date) as delivery_date,
			soi.stock_qty as ordered_qty, soi.delivered_qty, soi.rate, soi.amount
		from `tabSales Order` so
		join `tabSales Order Item` soi on soi.parent = so.name
		where {" and ".join(conditions)}
		order by so.transaction_date, so.name, soi.idx
		""",
		filters,
		as_dict=True,
	)
	invoiced = {}
	if rows:
		for r in frappe.db.sql(
			"""select so_detail, sum(stock_qty) qty from `tabSales Invoice Item`
			where docstatus = 1 and so_detail in %(rows)s group by so_detail""",
			{"rows": [r.so_detail for r in rows]},
			as_dict=True,
		):
			invoiced[r.so_detail] = flt(r.qty)

	out = []
	for r in rows:
		r.invoiced_qty = invoiced.get(r.so_detail, 0)
		r.pending_delivery = max(flt(r.ordered_qty) - flt(r.delivered_qty), 0)
		r.pending_invoice = max(flt(r.delivered_qty) - flt(r.invoiced_qty), 0)
		if r.delivered_qty <= 0:
			r.fulfilment = _("Not Delivered")
		elif r.pending_delivery > 0:
			r.fulfilment = _("Partially Delivered")
		elif r.pending_invoice > 0:
			r.fulfilment = _("Delivered, Not Invoiced")
		else:
			r.fulfilment = _("Completed")
		r.is_partial = 1 if 0 < flt(r.delivered_qty) < flt(r.ordered_qty) else 0
		r.days_overdue = date_diff(as_on, r.delivery_date) if r.pending_delivery and r.delivery_date else 0
		r.days_overdue = max(r.days_overdue, 0)
		r.overdue_flag = 1 if r.days_overdue > OVERDUE_DAYS else 0
		r.pending_value = r.pending_delivery * flt(r.rate)
		if filters.only_pending and not (r.pending_delivery or r.pending_invoice):
			continue
		if filters.only_overdue and not r.overdue_flag:
			continue
		out.append(r)
	return out


def get_columns():
	return [
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140},
		{"label": _("Customer"), "fieldname": "customer_name", "fieldtype": "Data", "width": 180},
		{"label": _("Location"), "fieldname": "branch", "fieldtype": "Data", "width": 95},
		{"label": _("Order Date"), "fieldname": "transaction_date", "fieldtype": "Date", "width": 95},
		{"label": _("Due Date"), "fieldname": "delivery_date", "fieldtype": "Date", "width": 95},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": _("Ordered"), "fieldname": "ordered_qty", "fieldtype": "Float", "width": 80},
		{"label": _("Delivered"), "fieldname": "delivered_qty", "fieldtype": "Float", "width": 85},
		{"label": _("Invoiced"), "fieldname": "invoiced_qty", "fieldtype": "Float", "width": 80},
		{"label": _("Pending Delivery"), "fieldname": "pending_delivery", "fieldtype": "Float", "width": 100},
		{"label": _("Pending Invoice"), "fieldname": "pending_invoice", "fieldtype": "Float", "width": 100},
		{"label": _("Pending Value"), "fieldname": "pending_value", "fieldtype": "Currency", "width": 115},
		{"label": _("Status"), "fieldname": "fulfilment", "fieldtype": "Data", "width": 150},
		{"label": _("Days Overdue"), "fieldname": "days_overdue", "fieldtype": "Int", "width": 90},
		{"label": _("Overdue > 5 d"), "fieldname": "overdue_flag", "fieldtype": "Check", "width": 90},
		{"label": _("Partial"), "fieldname": "is_partial", "fieldtype": "Check", "width": 65},
		{"label": _("Promise Risk"), "fieldname": "delivery_risk", "fieldtype": "Check", "width": 90},
	]


def get_chart(data):
	buckets = {}
	for r in data:
		buckets[r.fulfilment] = buckets.get(r.fulfilment, 0) + 1
	if not buckets:
		return None
	return {
		"data": {"labels": list(buckets), "datasets": [{"name": _("Order lines"), "values": list(buckets.values())}]},
		"type": "donut",
	}


def get_summary(data):
	return [
		{"label": _("Open lines"), "value": len([r for r in data if r.pending_delivery]), "indicator": "Blue"},
		{"label": _("Overdue > 5 days"), "value": len([r for r in data if r.overdue_flag]), "indicator": "Red"},
		{"label": _("Partially delivered"), "value": len([r for r in data if r.is_partial]), "indicator": "Orange"},
		{
			"label": _("Value pending delivery"),
			"value": sum(flt(r.pending_value) for r in data),
			"datatype": "Currency",
			"indicator": "Blue",
		},
	]
