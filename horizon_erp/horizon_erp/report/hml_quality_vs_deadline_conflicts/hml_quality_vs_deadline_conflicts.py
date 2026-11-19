"""HML Quality vs Deadline Conflicts - surface the clash before it is a crisis.

Top: open order lines due within the horizon whose QC-passed stock does not
cover the order while the linked Work Order has rework / audit hold / open
non-conformance / capacity shortfall. Bottom: the decision log.

KPI (summary): Quality-to-Delay Cost Ratio = cost of quality (rework +
expected failure cost) / cost of delay (LD + expedite) across decided cases.
Below 1: fixing quality was cheaper than being late - keep quality first.
Persistently above 1 on a product: invest in process capability there
(the defects are costing more than the delays they would cause).
"""

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.strategy.conflicts import at_risk_lines


def execute(filters=None):
	filters = frappe._dict(filters or {})
	horizon = int(filters.horizon_days or 7)
	data = []
	for r in at_risk_lines(horizon_days=horizon):
		qdd = frappe.db.get_value("Quality Deadline Decision", {"sales_order": r.sales_order, "item_code": r.item_code, "docstatus": ("<", 2)},
			["name", "decision", "docstatus"], as_dict=True)
		data.append(
			{
				"section": "At risk", "sales_order": r.sales_order, "customer": r.customer_name, "item_code": r.item_code,
				"delivery_date": r.delivery_date, "days_left": r.days_left, "pending": r.pending, "ready": r.ready,
				"reasons": "; ".join(r.reasons), "decision_doc": qdd.name if qdd else None,
				"decision": (qdd.decision or "Awaiting decision") if qdd else "Not raised yet",
			}
		)
	coq = cod = 0
	for d in frappe.get_all("Quality Deadline Decision", filters={"docstatus": ("<", 2)},
			fields=["name", "sales_order", "customer", "item_code", "delivery_date", "decision", "docstatus", "cost_of_quality",
				"cost_of_delay", "expedite_cost", "ship_now_qty", "new_delivery_date"], order_by="creation desc"):
		coq += flt(d.cost_of_quality)
		cod += flt(d.cost_of_delay) + flt(d.expedite_cost)
		data.append(
			{
				"section": "Decision log", "sales_order": d.sales_order, "customer": d.customer, "item_code": d.item_code,
				"delivery_date": d.delivery_date, "decision_doc": d.name, "decision": d.decision or "Open",
				"reasons": f"CoQ Rs {flt(d.cost_of_quality):,.0f} vs CoD Rs {flt(d.cost_of_delay) + flt(d.expedite_cost):,.0f}"
				+ (f"; ship {d.ship_now_qty:g} now, balance {frappe.format(d.new_delivery_date, 'Date')}" if d.ship_now_qty else ""),
			}
		)
	cols = [
		{"label": _("Section"), "fieldname": "section", "fieldtype": "Data", "width": 100},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Data", "width": 160},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 100},
		{"label": _("Due"), "fieldname": "delivery_date", "fieldtype": "Date", "width": 95},
		{"label": _("Days Left"), "fieldname": "days_left", "fieldtype": "Int", "width": 75},
		{"label": _("Pending"), "fieldname": "pending", "fieldtype": "Float", "width": 75},
		{"label": _("QC-passed Ready"), "fieldname": "ready", "fieldtype": "Float", "width": 110},
		{"label": _("Why / Cost"), "fieldname": "reasons", "fieldtype": "Data", "width": 330},
		{"label": _("Decision Record"), "fieldname": "decision_doc", "fieldtype": "Link", "options": "Quality Deadline Decision", "width": 140},
		{"label": _("Decision"), "fieldname": "decision", "fieldtype": "Data", "width": 200},
	]
	summary = [
		{"label": _("Lines at risk"), "value": len([d for d in data if d["section"] == "At risk"]), "indicator": "Red"},
		{"label": _("Cost of quality (decided)"), "value": coq, "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Cost of delay (decided)"), "value": cod, "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Quality-to-Delay Cost Ratio"), "value": round(coq / cod, 2) if cod else 0, "indicator": "Blue"},
	]
	return cols, data, None, None, summary
