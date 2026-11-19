"""HML Production Schedule - suggested sequence per line with capacity flags.

Sequencing rule (decision D-08):
1. Earliest deadline first (urgent customer orders first).
2. Among orders due within the same 3-day bucket, run the same item back to
   back so the changeover (setup) is paid once - saves setup hours.
3. Lines are loaded hour by hour from the start date using usable hours/day
   (working hours x (1 - downtime)); setup is charged only on an item change.

Each row shows projected start / finish and whether it finishes after its
deadline (LATE) - the conflict is visible days before it becomes a crisis.
Open Sales Order demand with no Work Order is listed at the bottom.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate, nowdate

from horizon_erp.constants import COMPANY
from horizon_erp.manufacturing.capacity import LINES, usable_hours_per_day

BUCKET_DAYS = 3


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start = getdate(filters.start_date or nowdate())
	wos = frappe.get_all(
		"Work Order",
		filters={"company": COMPANY, "docstatus": ("<", 2), "status": ("in", ["Draft", "Not Started", "In Process"])},
		fields=["name", "production_item", "qty", "produced_qty", "hml_production_line", "hml_deadline", "sales_order", "status",
			"hml_capacity_decision", "hml_audit_hold"],
	)
	data = []
	for line in LINES.values():
		rows = [w for w in wos if w.hml_production_line == line and flt(w.qty) > flt(w.produced_qty)]
		if filters.line and filters.line != line:
			continue
		data.extend(sequence_line(line, rows, start))
	data.extend(unplanned_demand())
	return get_columns(), data, None, None, summary(data)


def sequence_line(line, rows, start):
	def key(w):
		deadline = getdate(w.hml_deadline or add_days(start, 30))
		bucket = max(date_diff(deadline, start), -999) // BUCKET_DAYS
		return (bucket, w.production_item, deadline)

	rows = sorted(rows, key=key)
	per_day = usable_hours_per_day(line)
	setup_h = cint(frappe.get_cached_value("Workstation", line, "hml_setup_time_mins")) / 60
	clock = 0.0  # line hours consumed from `start`
	prev_item = None
	out = []
	for seq, w in enumerate(rows, 1):
		per_unit = flt(frappe.get_cached_value("Item", w.production_item, "hml_machine_hours_per_unit"))
		remaining = flt(w.qty) - flt(w.produced_qty)
		setup = 0 if w.production_item == prev_item else setup_h
		hours = per_unit * remaining + setup
		begin, clock = clock, clock + hours
		finish_day = add_days(start, int(clock // per_day)) if per_day else start
		start_day = add_days(start, int(begin // per_day)) if per_day else start
		late = bool(w.hml_deadline and getdate(finish_day) > getdate(w.hml_deadline))
		out.append(
			{
				"line": line,
				"seq": seq,
				"work_order": w.name,
				"item_code": w.production_item,
				"remaining_qty": remaining,
				"setup_hours": round(setup, 2),
				"run_hours": round(hours, 2),
				"projected_start": start_day,
				"projected_finish": finish_day,
				"deadline": w.hml_deadline,
				"late": 1 if late else 0,
				"days_late": max(date_diff(finish_day, w.hml_deadline), 0) if w.hml_deadline else 0,
				"sales_order": w.sales_order,
				"note": "On hold - audit < 70" if w.hml_audit_hold else (w.hml_capacity_decision or ("Draft - release to start" if w.status == "Draft" else "")),
			}
		)
		prev_item = w.production_item
	return out


def unplanned_demand():
	rows = frappe.db.sql(
		"""select so.name sales_order, soi.item_code, soi.stock_qty - soi.delivered_qty pending, soi.delivery_date
		from `tabSales Order Item` soi join `tabSales Order` so on so.name = soi.parent
		join `tabItem` i on i.name = soi.item_code
		where so.company = %s and so.docstatus = 1 and so.status not in ('Closed', 'Completed')
			and soi.stock_qty > soi.delivered_qty and ifnull(i.default_bom, '') != ''
			and not exists (select 1 from `tabWork Order` wo where wo.sales_order = so.name and wo.production_item = soi.item_code and wo.docstatus < 2)""",
		COMPANY,
		as_dict=True,
	)
	return [
		{
			"line": _("Unplanned"),
			"work_order": None,
			"item_code": r.item_code,
			"remaining_qty": r.pending,
			"deadline": r.delivery_date,
			"sales_order": r.sales_order,
			"note": _("Sales Order demand without a Work Order"),
			"late": 1 if r.delivery_date and getdate(r.delivery_date) < getdate(nowdate()) else 0,
		}
		for r in rows
	]


def summary(data):
	return [
		{"label": _("Work Orders sequenced"), "value": len([d for d in data if d.get("work_order")]), "indicator": "Blue"},
		{"label": _("Projected late"), "value": len([d for d in data if d.get("late") and d.get("work_order")]), "indicator": "Red"},
		{"label": _("Setup hours planned"), "value": round(sum(flt(d.get("setup_hours")) for d in data), 2), "indicator": "Orange"},
		{"label": _("Unplanned SO lines"), "value": len([d for d in data if not d.get("work_order")]), "indicator": "Orange"},
	]


def get_columns():
	return [
		{"label": _("Line"), "fieldname": "line", "fieldtype": "Data", "width": 110},
		{"label": _("Seq"), "fieldname": "seq", "fieldtype": "Int", "width": 50},
		{"label": _("Work Order"), "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 150},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Remaining Qty"), "fieldname": "remaining_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Setup h"), "fieldname": "setup_hours", "fieldtype": "Float", "width": 75},
		{"label": _("Load h"), "fieldname": "run_hours", "fieldtype": "Float", "width": 75},
		{"label": _("Projected Start"), "fieldname": "projected_start", "fieldtype": "Date", "width": 110},
		{"label": _("Projected Finish"), "fieldname": "projected_finish", "fieldtype": "Date", "width": 115},
		{"label": _("Deadline"), "fieldname": "deadline", "fieldtype": "Date", "width": 100},
		{"label": _("Late"), "fieldname": "late", "fieldtype": "Check", "width": 55},
		{"label": _("Days Late"), "fieldname": "days_late", "fieldtype": "Int", "width": 80},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140},
		{"label": _("Note"), "fieldname": "note", "fieldtype": "Data", "width": 230},
	]
