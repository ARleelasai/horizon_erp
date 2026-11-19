"""Quality vs deadline: detect the conflict early and force a decision.

scan_conflicts() (daily, and on failed in-process inspections) looks at every
open Sales Order line due within HORIZON_DAYS and checks whether it can
actually ship on time with goods that passed QC:
	ready = QC-passed finished stock available for the order
	risk  = ready < pending qty AND (a linked Work Order had rework / is on
	        audit hold / has an open non-conformance, or is over capacity)
For each new risk a Quality Deadline Decision is raised (status draft) and
the Sales Director, Operations Head, Quality and Finance are notified. The
system never silently blocks or silently ships - the people who own the
trade-off sign it.
"""

import frappe
from frappe.utils import add_days, date_diff, flt, getdate, nowdate

from horizon_erp.constants import COMPANY
from horizon_erp.notify import notify

HORIZON_DAYS = 3
ROLES = ("HML Sales Director", "HML Operations Head", "Quality Manager", "HML Finance Director")


def at_risk_lines(horizon_days=HORIZON_DAYS, today=None):
	today = getdate(today or nowdate())
	lines = frappe.db.sql(
		"""select so.name sales_order, so.customer_name, soi.item_code, soi.stock_qty - soi.delivered_qty pending,
			ifnull(soi.delivery_date, so.delivery_date) delivery_date
		from `tabSales Order` so join `tabSales Order Item` soi on soi.parent = so.name
		where so.company = %s and so.docstatus = 1 and so.status not in ('Closed', 'Completed')
			and soi.stock_qty > soi.delivered_qty
			and ifnull(soi.delivery_date, so.delivery_date) <= %s""",
		(COMPANY, add_days(today, horizon_days)),
		as_dict=True,
	)
	out = []
	for l in lines:
		wos = frappe.get_all(
			"Work Order",
			filters={"sales_order": l.sales_order, "production_item": l.item_code, "docstatus": ("<", 2)},
			fields=["name", "qty", "produced_qty", "hml_has_rework", "hml_rework_qty", "hml_audit_hold", "hml_capacity_status", "status"],
		)
		if not wos:
			continue
		ready = sum(flt(w.produced_qty) for w in wos)
		reasons = []
		for w in wos:
			if w.hml_has_rework:
				reasons.append(f"{w.name}: {flt(w.hml_rework_qty):g} unit(s) in rework")
			if w.hml_audit_hold:
				reasons.append(f"{w.name}: production audit hold")
			if w.hml_capacity_status and w.hml_capacity_status != "OK":
				reasons.append(f"{w.name}: over line capacity")
			if frappe.db.exists("Non Conformance", {"hml_work_order": w.name, "status": "Open"}):
				reasons.append(f"{w.name}: open non-conformance")
		if ready < flt(l.pending) and reasons:
			out.append(frappe._dict(**l, ready=ready, work_order=wos[0].name, reasons=reasons,
				days_left=date_diff(l.delivery_date, today), rework_qty=sum(flt(w.hml_rework_qty) for w in wos)))
	return out


def scan_conflicts(today=None):
	raised = []
	for r in at_risk_lines(today=today):
		if frappe.db.exists("Quality Deadline Decision", {"sales_order": r.sales_order, "item_code": r.item_code, "docstatus": ("<", 2)}):
			continue
		trigger = "Production Audit Hold" if any("audit" in x for x in r.reasons) else (
			"Capacity Shortfall" if any("capacity" in x for x in r.reasons) else "Inspection Failure")
		doc = frappe.get_doc(
			{
				"doctype": "Quality Deadline Decision",
				"company": COMPANY,
				"sales_order": r.sales_order,
				"item_code": r.item_code,
				"work_order": r.work_order,
				"trigger": trigger,
				"ready_qty": r.ready,
				"defective_qty": r.rework_qty,
				"operations_position": "; ".join(r.reasons),
			}
		).insert(ignore_permissions=True)
		raised.append(doc.name)
		users = []
		for role in ROLES:
			users += [u for u in frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
				if u not in ("Administrator",) and frappe.db.get_value("User", u, "enabled")]
		notify(
			sorted(set(users)),
			subject=f"Decision needed: {r.customer_name} {r.item_code} due in {r.days_left} day(s)",
			message=(
				f"<p>{r.sales_order}: {flt(r.pending):g} pending, only {r.ready:g} QC-passed and ready.</p>"
				f"<p>{'<br>'.join(r.reasons)}</p><p>Record positions and decide in {doc.name}.</p>"
			),
			reference_doctype="Quality Deadline Decision",
			reference_name=doc.name,
		)
	return {"raised": raised, "findings": raised}


def daily_scan():
	from horizon_erp.tasks.jobs import run_logged

	run_logged("Quality vs deadline scan", "horizon_erp.strategy.conflicts.scan_conflicts")
