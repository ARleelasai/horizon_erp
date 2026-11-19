"""HML Sales Pipeline: three views on one report (filter `view`).

* Leads by Status and Age: lead count and estimated value by status and age
  bucket (0-30 / 31-60 / 61-90 / 90+ days since creation).
* Quote Conversion: per month of quotation date - quotes, value, converted to
  Sales Order, conversion %, average days quote -> order (velocity).
* Open Pipeline: open opportunities and quotations with weighted value and a
  health flag (Expiring in 7 days / Stale > 45 days / Healthy).

The summary strip is the same on every view, so the report doubles as the
pipeline dashboard.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

from horizon_erp.constants import COMPANY

AGE_BUCKETS = [(0, 30, "0-30 d"), (31, 60, "31-60 d"), (61, 90, "61-90 d"), (91, 100000, "90+ d")]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.company or COMPANY
	filters.view = filters.view or "Open Pipeline"
	today = getdate(nowdate())
	if filters.view == "Leads by Status and Age":
		columns, data, chart = leads_view(filters, today)
	elif filters.view == "Quote Conversion":
		columns, data, chart = conversion_view(filters)
	else:
		columns, data, chart = pipeline_view(filters, today)
	return columns, data, None, chart, summary(filters, today)


# ------------------------------------------------------------------ leads


def leads_view(filters, today):
	leads = frappe.get_all(
		"Lead",
		filters={"company": filters.company},
		fields=["status", "creation", "hml_estimated_value"],
	)
	table = {}
	for l in leads:
		age = date_diff(today, getdate(l.creation))
		bucket = next(b[2] for b in AGE_BUCKETS if b[0] <= age <= b[1])
		row = table.setdefault(l.status, {"status": l.status, "total": 0, "value": 0})
		row[bucket] = row.get(bucket, 0) + 1
		row["total"] += 1
		row["value"] += flt(l.hml_estimated_value)
	data = sorted(table.values(), key=lambda r: -r["total"])
	columns = [{"label": _("Lead Status"), "fieldname": "status", "fieldtype": "Data", "width": 150}]
	columns += [{"label": b[2], "fieldname": b[2], "fieldtype": "Int", "width": 90} for b in AGE_BUCKETS]
	columns += [
		{"label": _("Total"), "fieldname": "total", "fieldtype": "Int", "width": 80},
		{"label": _("Estimated Value"), "fieldname": "value", "fieldtype": "Currency", "width": 140},
	]
	chart = {
		"data": {
			"labels": [r["status"] for r in data],
			"datasets": [{"name": b[2], "values": [r.get(b[2], 0) for r in data]} for b in AGE_BUCKETS],
		},
		"type": "bar",
		"barOptions": {"stacked": 1},
	}
	return columns, data, chart


# ------------------------------------------------------------- conversion


def _quotes_with_orders(company):
	quotes = frappe.get_all(
		"Quotation",
		filters={"company": company, "docstatus": 1},
		fields=["name", "transaction_date", "base_net_total", "status"],
	)
	first_order = {
		r.quotation: r
		for r in frappe.db.sql(
			"""select soi.prevdoc_docname as quotation, min(so.transaction_date) as order_date
			from `tabSales Order Item` soi join `tabSales Order` so on so.name = soi.parent
			where so.docstatus = 1 and so.company = %s and ifnull(soi.prevdoc_docname, '') != ''
			group by soi.prevdoc_docname""",
			company,
			as_dict=True,
		)
	}
	for q in quotes:
		o = first_order.get(q.name)
		q.order_date = o.order_date if o else None
		q.days_to_order = date_diff(o.order_date, q.transaction_date) if o else None
	return quotes


def conversion_view(filters):
	months = {}
	for q in _quotes_with_orders(filters.company):
		key = getdate(q.transaction_date).strftime("%Y-%m")
		m = months.setdefault(
			key,
			{"month": getdate(q.transaction_date).strftime("%b %Y"), "quotes": 0, "quote_value": 0, "converted": 0,
				"converted_value": 0, "expired": 0, "lost": 0, "_days": []},
		)
		m["quotes"] += 1
		m["quote_value"] += flt(q.base_net_total)
		if q.order_date:
			m["converted"] += 1
			m["converted_value"] += flt(q.base_net_total)
			m["_days"].append(q.days_to_order)
		elif q.status == "Expired":
			m["expired"] += 1
		elif q.status == "Lost":
			m["lost"] += 1
	data = []
	for key in sorted(months):
		m = months[key]
		m["conversion_pct"] = m["converted"] / m["quotes"] * 100 if m["quotes"] else 0
		m["avg_days_to_order"] = sum(m["_days"]) / len(m["_days"]) if m["_days"] else None
		m.pop("_days")
		data.append(m)
	columns = [
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 100},
		{"label": _("Quotes Sent"), "fieldname": "quotes", "fieldtype": "Int", "width": 100},
		{"label": _("Quote Value"), "fieldname": "quote_value", "fieldtype": "Currency", "width": 130},
		{"label": _("Converted"), "fieldname": "converted", "fieldtype": "Int", "width": 90},
		{"label": _("Converted Value"), "fieldname": "converted_value", "fieldtype": "Currency", "width": 130},
		{"label": _("Conversion %"), "fieldname": "conversion_pct", "fieldtype": "Percent", "width": 105},
		{"label": _("Avg Days to Order"), "fieldname": "avg_days_to_order", "fieldtype": "Float", "precision": 1, "width": 120},
		{"label": _("Expired"), "fieldname": "expired", "fieldtype": "Int", "width": 80},
		{"label": _("Lost"), "fieldname": "lost", "fieldtype": "Int", "width": 70},
	]
	chart = {
		"data": {
			"labels": [d["month"] for d in data],
			"datasets": [
				{"name": _("Quotes"), "values": [d["quotes"] for d in data], "chartType": "bar"},
				{"name": _("Converted"), "values": [d["converted"] for d in data], "chartType": "bar"},
			],
		},
		"type": "axis-mixed",
	}
	return columns, data, chart


# --------------------------------------------------------------- pipeline


def pipeline_view(filters, today):
	data = []
	for o in frappe.get_all(
		"Opportunity",
		filters={"company": filters.company, "status": ("in", ["Open", "Replied", "Quotation"])},
		fields=["name", "party_name", "customer_name", "sales_stage", "opportunity_amount", "probability",
			"expected_closing", "transaction_date"],
	):
		age = date_diff(today, o.transaction_date)
		data.append(
			{
				"document_type": "Opportunity",
				"document": o.name,
				"party": o.customer_name or o.party_name,
				"stage": o.sales_stage,
				"amount": flt(o.opportunity_amount),
				"probability": flt(o.probability),
				"weighted": flt(o.opportunity_amount) * flt(o.probability) / 100,
				"age_days": age,
				"closing": o.expected_closing,
				"health": _health(age, o.expected_closing, today),
			}
		)
	for q in frappe.get_all(
		"Quotation",
		filters={"company": filters.company, "docstatus": ("<", 2), "status": ("in", ["Draft", "Open", "Replied", "Partially Ordered"])},
		fields=["name", "customer_name", "party_name", "workflow_state", "base_net_total", "valid_till", "transaction_date", "docstatus"],
	):
		age = date_diff(today, q.transaction_date)
		prob = 50 if q.docstatus == 1 else 25
		data.append(
			{
				"document_type": "Quotation",
				"document": q.name,
				"party": q.customer_name or q.party_name,
				"stage": q.workflow_state or ("Sent" if q.docstatus else "Draft"),
				"amount": flt(q.base_net_total),
				"probability": prob,
				"weighted": flt(q.base_net_total) * prob / 100,
				"age_days": age,
				"closing": q.valid_till,
				"health": _health(age, q.valid_till, today),
			}
		)
	data.sort(key=lambda r: -r["weighted"])
	columns = [
		{"label": _("Type"), "fieldname": "document_type", "fieldtype": "Data", "width": 100},
		{"label": _("Document"), "fieldname": "document", "fieldtype": "Dynamic Link", "options": "document_type", "width": 160},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Data", "width": 190},
		{"label": _("Stage"), "fieldname": "stage", "fieldtype": "Data", "width": 170},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Probability %"), "fieldname": "probability", "fieldtype": "Percent", "width": 100},
		{"label": _("Weighted"), "fieldname": "weighted", "fieldtype": "Currency", "width": 120},
		{"label": _("Age (days)"), "fieldname": "age_days", "fieldtype": "Int", "width": 85},
		{"label": _("Closing / Valid Till"), "fieldname": "closing", "fieldtype": "Date", "width": 120},
		{"label": _("Health"), "fieldname": "health", "fieldtype": "Data", "width": 150},
	]
	health = {}
	for r in data:
		health[r["health"]] = health.get(r["health"], 0) + r["amount"]
	chart = {
		"data": {"labels": list(health), "datasets": [{"name": _("Value"), "values": list(health.values())}]},
		"type": "pie",
	}
	return columns, data, chart


def _health(age, closing, today):
	if closing and 0 <= date_diff(closing, today) <= 7:
		return _("Expiring in 7 days")
	if closing and date_diff(closing, today) < 0:
		return _("Past closing date")
	if age > 45:
		return _("Stale (> 45 days)")
	return _("Healthy")


def summary(filters, today):
	quotes = _quotes_with_orders(filters.company)
	converted = [q for q in quotes if q.order_date]
	open_value = sum(
		flt(v)
		for v in frappe.get_all(
			"Quotation",
			filters={"company": filters.company, "docstatus": 1, "status": ("in", ["Open", "Replied", "Partially Ordered"])},
			pluck="base_net_total",
		)
	)
	open_leads = frappe.db.count("Lead", {"company": filters.company, "status": ("in", ["Lead", "Open", "Replied", "Interested"])})
	return [
		{"label": _("Open leads"), "value": open_leads, "indicator": "Blue"},
		{"label": _("Outstanding quote value"), "value": open_value, "datatype": "Currency", "indicator": "Blue"},
		{
			"label": _("Quote-to-order conversion"),
			"value": round(len(converted) / len(quotes) * 100, 1) if quotes else 0,
			"datatype": "Percent",
			"indicator": "Green",
		},
		{
			"label": _("Avg days quote to order"),
			"value": round(sum(q.days_to_order for q in converted) / len(converted), 1) if converted else 0,
			"indicator": "Orange",
		},
	]
