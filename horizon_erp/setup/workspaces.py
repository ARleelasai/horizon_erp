"""Workspaces, number cards and dashboard charts (built by code on migrate).

Kept as non-standard records generated from this file, so the definitions
live in the repo without the export noise of developer-mode JSON.
	Horizon ERP    - the hub: every Horizon report and form, by area
	HML Warehouse  - today's deliveries and packing priority
	HML Quality    - today's audit queue, corrective actions, inspections
	HML Finance    - approvals waiting, budget, bank, GST
"""

import json

import frappe

from horizon_erp.constants import COMPANY

C = json.dumps


def _filters(*conds):
	return C([["{0}".format(dt), f, op, v, False] for dt, f, op, v in conds])


NUMBER_CARDS = [
	# name, doctype, function, aggregate field, filters, dynamic filters, color
	("HML Deliveries Today", "Delivery Note", "Count", None,
		[("Delivery Note", "company", "=", COMPANY), ("Delivery Note", "docstatus", "<", 2)],
		[["Delivery Note", "posting_date", "=", "frappe.datetime.get_today()"]], "#2e6bc6"),
	("HML Open Pick Lists", "Pick List", "Count", None,
		[("Pick List", "company", "=", COMPANY), ("Pick List", "status", "in", ["Draft", "Open"])], [], "#f0ad4e"),
	("HML Orders To Deliver", "Sales Order", "Count", None,
		[("Sales Order", "company", "=", COMPANY), ("Sales Order", "status", "in", ["To Deliver and Bill", "To Deliver"])], [], "#e24c4c"),
	("HML Audits Today", "Production Audit", "Count", None, [], [["Production Audit", "audit_date", "=", "frappe.datetime.get_today()"]], "#2e6bc6"),
	("HML Open Corrective Actions", "Corrective Action", "Count", None,
		[("Corrective Action", "status", "in", ["Open", "In Progress"])], [], "#f0ad4e"),
	("HML Overdue Corrective Actions", "Corrective Action", "Count", None,
		[("Corrective Action", "is_overdue", "=", 1)], [], "#e24c4c"),
	("HML POs Awaiting Approval", "Purchase Order", "Count", None,
		[("Purchase Order", "company", "=", COMPANY), ("Purchase Order", "workflow_state", "like", "Pending%")], [], "#f0ad4e"),
	("HML PO Value Awaiting Approval", "Purchase Order", "Sum", "base_grand_total",
		[("Purchase Order", "company", "=", COMPANY), ("Purchase Order", "workflow_state", "like", "Pending%")], [], "#f0ad4e"),
	("HML Open Quotation Value", "Quotation", "Sum", "base_net_total",
		[("Quotation", "company", "=", COMPANY), ("Quotation", "status", "in", ["Open", "Replied"]), ("Quotation", "docstatus", "=", 1)], [], "#2e6bc6"),
	("HML Quality-Deadline Decisions Open", "Quality Deadline Decision", "Count", None,
		[("Quality Deadline Decision", "docstatus", "=", 0)], [], "#e24c4c"),
	("HML Stock Value", "Bin", "Sum", "stock_value", [("Bin", "warehouse", "like", "% - HML")], [], "#28a745"),
	("HML Receivables", "Sales Invoice", "Sum", "outstanding_amount",
		[("Sales Invoice", "company", "=", COMPANY), ("Sales Invoice", "docstatus", "=", 1)], [], "#2e6bc6"),
]

CHARTS = [
	# name, doctype, type, based_on / group_by, value field, aggregate, chart type, filters
	("HML Sales Order Value by Month", "Sales Order", "Sum", "transaction_date", "base_net_total", None, "Bar",
		[("Sales Order", "company", "=", COMPANY), ("Sales Order", "docstatus", "=", 1)]),
	("HML Audit Score by Line", "Production Audit", "Group By", "production_line", "audit_score", "Average", "Bar",
		[("Production Audit", "docstatus", "=", 1)]),
	("HML Inspections by Result", "Quality Inspection", "Group By", "hml_result", None, "Count", "Donut",
		[("Quality Inspection", "docstatus", "=", 1), ("Quality Inspection", "hml_result", "is", "set")]),
]

WORKSPACES = {
	"Horizon ERP": {
		"icon": "organization",
		"cards": ["HML Open Quotation Value", "HML Orders To Deliver", "HML POs Awaiting Approval", "HML Quality-Deadline Decisions Open",
			"HML Stock Value", "HML Receivables"],
		"charts": ["HML Sales Order Value by Month"],
		"shortcuts": [("Quotation", "DocType"), ("Sales Order", "DocType"), ("Purchase Order", "DocType"), ("Work Order", "DocType"),
			("Production Audit", "DocType"), ("Quality Deadline Decision", "DocType")],
		"link_cards": {
			"Setup and Inventory": ["HML Consolidated Inventory", "Cost Center Wise Profit and Loss", "HML Inventory Health", "Inventory Obsolescence Analysis"],
			"Selling": ["HML Sales Pipeline", "HML Price List Comparison", "HML Order Fulfilment Status"],
			"Buying and Planning": ["HML Purchase Approval Queue", "HML Approval Audit Report", "HML Incoming Quality Analysis",
				"HML Supplier Quality Scorecard", "HML Demand Forecast vs Actual"],
			"Manufacturing": ["HML BOM Explosion", "HML Production Schedule", "HML Production Dashboard", "HML Production Cost Variance"],
			"Quality": ["HML Quality Metrics", "HML Corrective Action Tracker", "Audit Findings Dashboard", "HML Quality vs Deadline Conflicts"],
			"Projects, Assets, HR": ["HML Project Dashboard", "HML Asset Register", "HML Leave Balance with Expiry", "HML Salary Cost Analysis",
				"HML Statutory Compliance Summary"],
			"Finance and Tax": ["HML Bank Reconciliation Statement", "HML Budget Variance", "HML Budget Performance Analysis",
				"HML Location PnL vs Budget", "HML GST Summary by Registration", "HML GSTR-1 vs Sales Order Reconciliation", "HML Audit Trail"],
			"Strategy and BI": ["HML Net Party Position", "HML Migration Data Validation", "HML Product Profitability", "HML Customer Profitability",
				"HML Sales Trend and Forecast", "HML API Usage"],
			"Horizon Records": ["DocType:Discount Approval Log", "DocType:Supplier Blacklist Exception", "DocType:Quarterly Purchase Plan",
				"DocType:Corrective Action", "DocType:Maintenance Job", "DocType:Payment Batch", "DocType:Budget Overage Approval",
				"DocType:Bank Reconciliation Lock", "DocType:Scrap Note", "DocType:Migration Staging Row", "DocType:Integration Log",
				"DocType:API Client", "DocType:API Request Log"],
		},
	},
	"HML Warehouse": {
		"icon": "stock",
		"cards": ["HML Deliveries Today", "HML Open Pick Lists", "HML Orders To Deliver"],
		"quick_lists": [
			("Pick List", "Packing queue (open pick lists)", [["Pick List", "company", "=", COMPANY], ["Pick List", "status", "in", ["Draft", "Open"]]]),
			("Sales Order", "Orders by promised date", [["Sales Order", "company", "=", COMPANY], ["Sales Order", "status", "in", ["To Deliver and Bill", "To Deliver"]]]),
			("Delivery Note", "Today's deliveries", [["Delivery Note", "company", "=", COMPANY], ["Delivery Note", "posting_date", "Timespan", "today"]]),
		],
		"shortcuts": [("Pick List", "DocType"), ("Delivery Note", "DocType"), ("Stock Entry", "DocType"), ("HML Order Fulfilment Status", "Report"),
			("HML Consolidated Inventory", "Report")],
		"link_cards": {"Warehouse Reports": ["HML Order Fulfilment Status", "HML Consolidated Inventory", "HML Inventory Health"]},
	},
	"HML Quality": {
		"icon": "quality",
		"cards": ["HML Audits Today", "HML Open Corrective Actions", "HML Overdue Corrective Actions", "HML Quality-Deadline Decisions Open"],
		"charts": ["HML Audit Score by Line", "HML Inspections by Result"],
		"quick_lists": [
			("Production Audit", "Today's audit queue", [["Production Audit", "audit_date", "Timespan", "today"]]),
			("Corrective Action", "Open corrective actions", [["Corrective Action", "status", "in", ["Open", "In Progress"]]]),
			("Quality Inspection", "Inspections awaiting submission", [["Quality Inspection", "docstatus", "=", 0]]),
		],
		"shortcuts": [("Production Audit", "DocType"), ("Quality Inspection", "DocType"), ("Non Conformance", "DocType"),
			("Corrective Action", "DocType"), ("Audit Findings Dashboard", "Report")],
		"link_cards": {"Quality Reports": ["Audit Findings Dashboard", "HML Quality Metrics", "HML Corrective Action Tracker",
			"HML Incoming Quality Analysis", "HML Supplier Quality Scorecard", "HML Quality vs Deadline Conflicts"]},
	},
	"HML Finance": {
		"icon": "accounting",
		"cards": ["HML POs Awaiting Approval", "HML PO Value Awaiting Approval", "HML Receivables"],
		"shortcuts": [("HML Purchase Approval Queue", "Report"), ("Payment Batch", "DocType"), ("Budget Overage Approval", "DocType"),
			("Bank Reconciliation Lock", "DocType"), ("Bank Reconciliation Tool", "DocType")],
		"link_cards": {"Finance Reports": ["HML Purchase Approval Queue", "HML Approval Audit Report", "HML Budget Variance",
			"HML Budget Performance Analysis", "HML Bank Reconciliation Statement", "HML Location PnL vs Budget",
			"Cost Center Wise Profit and Loss", "HML GST Summary by Registration", "HML Audit Trail", "HML Net Party Position"]},
	},
}


def make_all():
	for name, dt, fn, field, filters, dyn, color in NUMBER_CARDS:
		doc = frappe.get_doc("Number Card", name) if frappe.db.exists("Number Card", name) else frappe.new_doc("Number Card")
		doc.update({
			"label": name.replace("HML ", ""), "type": "Document Type", "document_type": dt, "function": fn,
			"aggregate_function_based_on": field, "filters_json": C([[a, b, c, d, False] for a, b, c, d in filters]),
			"dynamic_filters_json": C([[a, b, c, d] for a, b, c, d in dyn]) if dyn else "[]", "is_public": 1,
			"show_percentage_stats": 0, "color": color, "module": "Horizon ERP", "is_standard": 0,
		})
		doc.name = name
		doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True, set_name=name)
	for name, dt, ctype, based_on, value, agg, chart_type, filters in CHARTS:
		doc = frappe.get_doc("Dashboard Chart", name) if frappe.db.exists("Dashboard Chart", name) else frappe.new_doc("Dashboard Chart")
		values = {
			"chart_name": name, "chart_type": ctype, "document_type": dt, "type": chart_type, "is_public": 1, "module": "Horizon ERP",
			"is_standard": 0, "filters_json": C([[a, b, c, d, False] for a, b, c, d in filters]), "timeseries": 0,
		}
		if ctype == "Group By":
			values.update({"group_by_type": agg, "group_by_based_on": based_on, "aggregate_function_based_on": value})
		else:
			values.update({"based_on": based_on, "value_based_on": value, "timeseries": 1, "time_interval": "Monthly", "timespan": "Last Year"})
		doc.update(values)
		doc.save(ignore_permissions=True) if not doc.is_new() else doc.insert(ignore_permissions=True)
	for ws_name, spec in WORKSPACES.items():
		_make_workspace(ws_name, spec)


def _make_workspace(name, spec):
	doc = frappe.get_doc("Workspace", name) if frappe.db.exists("Workspace", name) else frappe.new_doc("Workspace")
	doc.update({"label": name, "title": name, "module": "Horizon ERP", "public": 1, "is_hidden": 0, "icon": spec.get("icon"),
		"sequence_id": 50, "content": "[]"})
	for table in ("number_cards", "charts", "shortcuts", "links", "quick_lists"):
		doc.set(table, [])
	blocks = [{"id": f"h{name[:3]}", "type": "header", "data": {"text": f'<span class="h4"><b>{name}</b></span>', "col": 12}}]
	for i, card in enumerate(spec.get("cards", [])):
		doc.append("number_cards", {"number_card_name": card, "label": card.replace("HML ", "")})
		blocks.append({"id": f"nc{i}", "type": "number_card", "data": {"number_card_name": card, "col": 4}})
	for i, chart in enumerate(spec.get("charts", [])):
		doc.append("charts", {"chart_name": chart, "label": chart.replace("HML ", "")})
		blocks.append({"id": f"ch{i}", "type": "chart", "data": {"chart_name": chart, "col": 12 if len(spec["charts"]) == 1 else 6}})
	if spec.get("shortcuts"):
		blocks.append({"id": "hs", "type": "header", "data": {"text": '<span class="h5">Shortcuts</span>', "col": 12}})
	for i, (target, kind) in enumerate(spec.get("shortcuts", [])):
		label = target.replace("HML ", "")
		doc.append("shortcuts", {"label": label, "type": kind, "link_to": target, "doc_view": "List" if kind == "DocType" else "",
			"color": "Grey"})
		blocks.append({"id": f"sc{i}", "type": "shortcut", "data": {"shortcut_name": label, "col": 3}})
	for i, (dt, label, filters) in enumerate(spec.get("quick_lists", [])):
		doc.append("quick_lists", {"document_type": dt, "label": label, "quick_list_filter": C(filters)})
		blocks.append({"id": f"ql{i}", "type": "quick_list", "data": {"quick_list_name": label, "col": 4}})
	if spec.get("link_cards"):
		blocks.append({"id": "hr", "type": "header", "data": {"text": '<span class="h5">Reports and Records</span>', "col": 12}})
	for i, (card, links) in enumerate(spec.get("link_cards", {}).items()):
		doc.append("links", {"type": "Card Break", "label": card, "link_count": len(links)})
		for link in links:
			if link.startswith("DocType:"):
				dt = link.split(":", 1)[1]
				doc.append("links", {"type": "Link", "label": dt, "link_type": "DocType", "link_to": dt})
			else:
				doc.append("links", {"type": "Link", "label": link.replace("HML ", ""), "link_type": "Report", "link_to": link,
					"is_query_report": 1})
		blocks.append({"id": f"lc{i}", "type": "card", "data": {"card_name": card, "col": 4}})
	doc.content = C(blocks)
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
