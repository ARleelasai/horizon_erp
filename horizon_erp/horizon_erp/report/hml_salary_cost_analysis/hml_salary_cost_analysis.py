"""HML Salary Cost Analysis - by department, grade or pay category.

Cost to company = gross pay + employer PF + employer ESI (statistical
components). Grouping is selectable, so one report answers the three cuts.
"""

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.constants import COMPANY


def execute(filters=None):
	filters = frappe._dict(filters or {})
	group_by = {"Department": "ss.department", "Grade": "e.grade", "Pay Category": "e.hml_employee_category", "Branch": "ss.branch"}[
		filters.group_by or "Department"
	]
	rows = frappe.db.sql(
		f"""
		select ifnull({group_by}, 'Not set') grp, count(distinct ss.employee) headcount,
			sum(ss.gross_pay) gross, sum(ss.total_deduction) deductions, sum(ss.net_pay) net,
			sum((select ifnull(sum(sd.amount), 0) from `tabSalary Detail` sd where sd.parent = ss.name
				and sd.salary_component in ('PF Employer', 'ESI Employer'))) employer,
			sum((select ifnull(sum(sd.amount), 0) from `tabSalary Detail` sd where sd.parent = ss.name
				and sd.salary_component = 'Overtime')) overtime
		from `tabSalary Slip` ss join `tabEmployee` e on e.name = ss.employee
		where ss.docstatus = 1 and ss.company = %(company)s and ss.start_date >= %(from_date)s and ss.end_date <= %(to_date)s
		group by grp order by gross desc
		""",
		{"company": COMPANY, "from_date": filters.from_date or "2026-04-01", "to_date": filters.to_date or "2027-03-31"},
		as_dict=True,
	)
	total_ctc = sum(flt(r.gross) + flt(r.employer) for r in rows)
	for r in rows:
		r.ctc = flt(r.gross) + flt(r.employer)
		r.share = r.ctc / total_ctc * 100 if total_ctc else 0
		r.avg_ctc = r.ctc / r.headcount if r.headcount else 0
	columns = [
		{"label": filters.group_by or _("Department"), "fieldname": "grp", "fieldtype": "Data", "width": 190},
		{"label": _("Headcount"), "fieldname": "headcount", "fieldtype": "Int", "width": 90},
		{"label": _("Gross Pay"), "fieldname": "gross", "fieldtype": "Currency", "width": 130},
		{"label": _("of which Overtime"), "fieldname": "overtime", "fieldtype": "Currency", "width": 125},
		{"label": _("Employer PF + ESI"), "fieldname": "employer", "fieldtype": "Currency", "width": 130},
		{"label": _("Cost to Company"), "fieldname": "ctc", "fieldtype": "Currency", "width": 135},
		{"label": _("Avg CTC / Head"), "fieldname": "avg_ctc", "fieldtype": "Currency", "width": 120},
		{"label": _("Share %"), "fieldname": "share", "fieldtype": "Percent", "width": 80},
		{"label": _("Deductions"), "fieldname": "deductions", "fieldtype": "Currency", "width": 120},
		{"label": _("Net Pay"), "fieldname": "net", "fieldtype": "Currency", "width": 120},
	]
	chart = {"data": {"labels": [r.grp for r in rows], "datasets": [{"name": _("Cost to Company"), "values": [r.ctc for r in rows]}]}, "type": "pie"}
	return columns, rows, None, chart
