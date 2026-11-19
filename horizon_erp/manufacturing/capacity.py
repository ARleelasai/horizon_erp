"""Line capacity check on Work Order (Horizon only).

Capacity model (decision D-08):
	usable hours per day  = Workstation working hours x (1 - planned downtime %)
	required hours        = qty x Item.hml_machine_hours_per_unit + setup time
	free hours            = usable hours from planned start to deadline
	                        - remaining hours of every other open WO on the line
	                          that starts on or before the deadline (late WOs
	                          still occupy the line, so they count too)

If no eligible line has enough free hours, saving the Work Order fails with
the numbers and the four business options, unless a Capacity Decision and a
note are recorded on the WO. The conflict is never silently absorbed.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate

from horizon_erp.constants import is_hml

LINES = {"Line A": "HML Line A", "Line B": "HML Line B"}
DISPATCH_DAYS = 2
OPEN_STATUSES = ("Not Started", "In Process", "Draft")


def usable_hours_per_day(workstation):
	ws = frappe.get_cached_doc("Workstation", workstation)
	hours = 0
	for wh in ws.working_hours:
		hours += flt(frappe.utils.time_diff_in_hours(wh.end_time, wh.start_time))
	hours = hours or 16
	return round(hours * (1 - flt(ws.hml_downtime_pct) / 100), 2)


def eligible_lines(item_code):
	pref = frappe.get_cached_value("Item", item_code, "hml_eligible_lines") or "Any"
	if pref in LINES:
		return [LINES[pref]]
	return list(LINES.values())


def required_hours(item_code, qty, workstation):
	per_unit = flt(frappe.get_cached_value("Item", item_code, "hml_machine_hours_per_unit"))
	setup = cint(frappe.get_cached_value("Workstation", workstation, "hml_setup_time_mins")) / 60
	return round(per_unit * flt(qty) + setup, 2)


def booked_hours(workstation, start, end, exclude=None):
	rows = frappe.db.sql(
		"""select name, production_item, qty, produced_qty, planned_start_date, hml_deadline
		from `tabWork Order`
		where hml_production_line = %s and docstatus < 2 and status in %s and name != %s
			and date(planned_start_date) <= %s""",
		(workstation, OPEN_STATUSES, exclude or "", end),
		as_dict=True,
	)
	total = 0
	for r in rows:
		remaining = max(flt(r.qty) - flt(r.produced_qty), 0)
		total += required_hours(r.production_item, remaining, workstation)
	return round(total, 2), rows


def free_hours(workstation, start, end, exclude=None):
	days = max(date_diff(end, start) + 1, 1)
	capacity = usable_hours_per_day(workstation) * days
	booked, _rows = booked_hours(workstation, start, end, exclude)
	return round(capacity - booked, 2), capacity, booked


def deadline_for(doc):
	if doc.sales_order:
		so_date = frappe.db.get_value("Sales Order", doc.sales_order, "delivery_date")
		if so_date:
			return add_days(so_date, -DISPATCH_DAYS)
	if doc.planned_end_date:
		return getdate(doc.planned_end_date)
	lead = cint(frappe.get_cached_value("Item", doc.production_item, "hml_mfg_lead_time_days")) or 7
	return add_days(getdate(doc.planned_start_date), lead)


def validate_work_order(doc, method=None):
	if not is_hml(doc) or doc.docstatus == 2:
		return
	if not flt(frappe.get_cached_value("Item", doc.production_item, "hml_machine_hours_per_unit")):
		return  # item not line-planned
	start = getdate(doc.planned_start_date)
	doc.hml_deadline = doc.hml_deadline or deadline_for(doc)
	end = getdate(doc.hml_deadline)
	if end < start:
		end = start

	candidates = [doc.hml_production_line] if doc.hml_production_line else eligible_lines(doc.production_item)
	best = None
	for line in candidates:
		need = required_hours(doc.production_item, flt(doc.qty) - flt(doc.produced_qty), line)
		free, capacity, booked = free_hours(line, start, end, exclude=doc.name)
		if best is None or free - need > best[1] - best[2]:
			best = (line, free, need, capacity, booked)
	line, free, need, capacity, booked = best
	doc.hml_production_line = line
	doc.hml_required_hours = need
	doc.hml_line_free_hours = free

	if need <= free:
		doc.hml_capacity_status = "OK"
		return
	if doc.hml_capacity_decision and (doc.hml_capacity_decision_note or "").strip():
		doc.hml_capacity_status = "Over Capacity - Decision Recorded"
		doc.hml_decided_by = doc.hml_decided_by or frappe.session.user
		return
	frappe.throw(
		_(
			"<b>Capacity conflict on {0}.</b><br>"
			"Needs {1} h between {2} and {3}; the line has {4} usable hours, {5} h already booked, so only {6} h are free.<br><br>"
			"Pick one and record it in <b>Capacity Decision</b> with a note:<br>"
			"&bull; Ship Partial - produce what fits, ship the balance later<br>"
			"&bull; Delay Delivery - move the date with the customer's agreement<br>"
			"&bull; Overtime / Extra Shift - add hours (cost)<br>"
			"&bull; Move to Other Line - if the product can run there<br>"
			"&bull; Negotiate Timeline - Sales to agree a new date"
		).format(line, need, frappe.format(start, "Date"), frappe.format(end, "Date"), capacity, booked, max(free, 0)),
		title=_("Line fully booked"),
	)
