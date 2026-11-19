"""HML Leave Balance with Expiry.

Per employee and leave type for the leave period: opening (carried forward +
new allocation), used, available, and the expiry date of carried-forward
leaves (from the Leave Ledger), so staff can use them before they lapse.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from horizon_erp.constants import COMPANY


def execute(filters=None):
	filters = frappe._dict(filters or {})
	on = getdate(filters.date or nowdate())
	rows = frappe.db.sql(
		"""
		select la.employee, la.employee_name, e.department, la.leave_type, la.from_date, la.to_date,
			la.new_leaves_allocated, la.carry_forwarded_leaves_count, la.total_leaves_allocated
		from `tabLeave Allocation` la join `tabEmployee` e on e.name = la.employee
		where la.docstatus = 1 and e.company = %s and %s between la.from_date and la.to_date
		order by e.department, la.employee_name, la.leave_type
		""",
		(COMPANY, on),
		as_dict=True,
	)
	data = []
	for r in rows:
		used = -flt(
			frappe.db.sql(
				"""select sum(leaves) from `tabLeave Ledger Entry`
				where employee = %s and leave_type = %s and transaction_type = 'Leave Application' and docstatus = 1
					and from_date between %s and %s""",
				(r.employee, r.leave_type, r.from_date, r.to_date),
			)[0][0]
		)
		expiry = frappe.db.get_value(
			"Leave Ledger Entry",
			{"employee": r.employee, "leave_type": r.leave_type, "is_carry_forward": 1, "docstatus": 1, "from_date": (">=", r.from_date)},
			"to_date",
		)
		data.append(
			{
				"employee": r.employee,
				"employee_name": r.employee_name,
				"department": r.department,
				"leave_type": r.leave_type,
				"carried_forward": flt(r.carry_forwarded_leaves_count),
				"new_allocation": flt(r.new_leaves_allocated),
				"opening": flt(r.total_leaves_allocated),
				"used": used,
				"available": flt(r.total_leaves_allocated) - used,
				"cf_expiry": expiry if flt(r.carry_forwarded_leaves_count) else None,
			}
		)
	columns = [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
		{"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 150},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Data", "width": 150},
		{"label": _("Leave Type"), "fieldname": "leave_type", "fieldtype": "Link", "options": "Leave Type", "width": 140},
		{"label": _("Carried Forward"), "fieldname": "carried_forward", "fieldtype": "Float", "width": 110},
		{"label": _("New Allocation"), "fieldname": "new_allocation", "fieldtype": "Float", "width": 110},
		{"label": _("Opening Balance"), "fieldname": "opening", "fieldtype": "Float", "width": 110},
		{"label": _("Used"), "fieldname": "used", "fieldtype": "Float", "width": 70},
		{"label": _("Available"), "fieldname": "available", "fieldtype": "Float", "width": 85},
		{"label": _("Carry-forward Expires"), "fieldname": "cf_expiry", "fieldtype": "Date", "width": 140},
	]
	return columns, data
