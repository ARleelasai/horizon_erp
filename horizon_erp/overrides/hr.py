"""HR and payroll rules for Horizon.

* Employee: pay category mandatory (drives salary structure).
* Leave approval: besides HRMS's own balance and overlap checks, a leave is
  not approved if it would take more than 25 % of the same department off on
  any day of the leave - the "conflicting leaves" rule for a two-shift plant.
* Salary Slip: fills hours worked and overtime from Attendance (+ timesheet
  overtime) before HRMS evaluates the wage-earner formulas
  (Basic Wages = base x hml_hours_worked, Overtime = base x 2 x hml_overtime_hours).
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate

from horizon_erp.constants import COMPANY, is_hml

MAX_DEPARTMENT_ABSENCE = 0.25
STANDARD_DAY_HOURS = 8


def validate_employee(doc, method=None):
	if is_hml(doc) and doc.status == "Active" and not doc.hml_employee_category:
		frappe.throw(_("Select the Pay Category (Salaried Staff / Wage Earner / Contractual)."))


def validate_leave_application(doc, method=None):
	if not is_hml(doc) or doc.status != "Approved" or not doc.department:
		return
	team = frappe.db.count("Employee", {"department": doc.department, "status": "Active", "company": COMPANY})
	if team < 4:
		return  # rule meaningless for tiny teams
	limit = int(team * MAX_DEPARTMENT_ABSENCE)
	day = getdate(doc.from_date)
	while day <= getdate(doc.to_date):
		others = frappe.db.sql(
			"""select count(distinct employee) from `tabLeave Application`
			where department = %s and status = 'Approved' and docstatus < 2 and employee != %s
				and %s between from_date and to_date""",
			(doc.department, doc.employee, day),
		)[0][0]
		if others + 1 > limit:
			frappe.throw(
				_("Cannot approve: {0} of {1} people in {2} would be on leave on {3} (limit {4}). Approve after rescheduling a conflicting leave.").format(
					others + 1, team, doc.department, frappe.format(day, "Date"), limit
				),
				title=_("Conflicting leaves"),
			)
		day = add_days(day, 1)


def before_validate_salary_slip(doc, method=None):
	if not is_hml(doc) or not doc.employee:
		return
	doc.hml_employee_category = frappe.db.get_value("Employee", doc.employee, "hml_employee_category")
	if doc.hml_employee_category != "Wage Earner":
		return
	rows = frappe.get_all(
		"Attendance",
		filters={"employee": doc.employee, "docstatus": 1, "status": ("in", ["Present", "Half Day", "Work From Home"]),
			"attendance_date": ("between", [doc.start_date, doc.end_date])},
		fields=["attendance_date", "working_hours", "status"],
	)
	hours = overtime = 0
	for r in rows:
		wh = flt(r.working_hours) or (STANDARD_DAY_HOURS / 2 if r.status == "Half Day" else STANDARD_DAY_HOURS)
		hours += min(wh, STANDARD_DAY_HOURS)
		overtime += max(wh - STANDARD_DAY_HOURS, 0)
	doc.hml_hours_worked = round(hours, 2)
	doc.hml_overtime_hours = round(overtime, 2)
