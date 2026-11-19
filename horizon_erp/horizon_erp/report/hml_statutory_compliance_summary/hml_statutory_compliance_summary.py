"""HML Statutory Compliance Summary - PF, ESI, PT and TDS per employee.

PF: wages = min(Basic + DA (or Basic Wages), 15,000); employee 12 %, employer
12 % (split 3.67 % EPF + 8.33 % EPS shown for the ECR). ESI: applicable when
gross <= 21,000; employee 0.75 %, employer 3.25 %. PT: Maharashtra slab;
Delhi does not levy PT. TDS: income tax on salary + 10 % on contract fees.
"""

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.constants import COMPANY

COMPONENTS = {
	"Provident Fund": "pf_employee", "PF Employer": "pf_employer", "ESI Employee": "esi_employee", "ESI Employer": "esi_employer",
	"Professional Tax": "pt", "Income Tax": "tds_salary", "TDS on Contract Fee": "tds_contract",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	slips = frappe.get_all(
		"Salary Slip",
		filters={"company": COMPANY, "docstatus": 1, "start_date": (">=", filters.from_date or "2026-10-01"),
			"end_date": ("<=", filters.to_date or "2026-10-31")},
		fields=["name", "employee", "employee_name", "branch", "gross_pay"],
	)
	data = []
	for s in slips:
		row = {"employee": s.employee, "employee_name": s.employee_name, "branch": s.branch, "gross": s.gross_pay,
			"uan": frappe.db.get_value("Employee", s.employee, "provident_fund_account")}
		for d in frappe.get_all("Salary Detail", filters={"parent": s.name}, fields=["salary_component", "amount"]):
			if d.salary_component in COMPONENTS:
				row[COMPONENTS[d.salary_component]] = flt(d.amount)
		row["pf_wages"] = round(flt(row.get("pf_employee")) / 0.12, 0) if row.get("pf_employee") else 0
		row["eps"] = round(min(row["pf_wages"], 15000) * 0.0833, 0) if row["pf_wages"] else 0
		row["epf_er"] = flt(row.get("pf_employer")) - row["eps"]
		row["esi_applicable"] = 1 if row.get("esi_employee") else 0
		data.append(row)
	data.sort(key=lambda r: r["employee_name"])
	columns = [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 115},
		{"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 140},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Data", "width": 95},
		{"label": _("PF A/c / UAN"), "fieldname": "uan", "fieldtype": "Data", "width": 150},
		{"label": _("Gross"), "fieldname": "gross", "fieldtype": "Currency", "width": 105},
		{"label": _("PF Wages"), "fieldname": "pf_wages", "fieldtype": "Currency", "width": 95},
		{"label": _("PF Employee 12 %"), "fieldname": "pf_employee", "fieldtype": "Currency", "width": 115},
		{"label": _("EPF Employer 3.67 %"), "fieldname": "epf_er", "fieldtype": "Currency", "width": 125},
		{"label": _("EPS 8.33 %"), "fieldname": "eps", "fieldtype": "Currency", "width": 95},
		{"label": _("ESI Applicable"), "fieldname": "esi_applicable", "fieldtype": "Check", "width": 95},
		{"label": _("ESI Employee 0.75 %"), "fieldname": "esi_employee", "fieldtype": "Currency", "width": 125},
		{"label": _("ESI Employer 3.25 %"), "fieldname": "esi_employer", "fieldtype": "Currency", "width": 125},
		{"label": _("Professional Tax"), "fieldname": "pt", "fieldtype": "Currency", "width": 110},
		{"label": _("TDS (Salary)"), "fieldname": "tds_salary", "fieldtype": "Currency", "width": 110},
		{"label": _("TDS (Contract 10 %)"), "fieldname": "tds_contract", "fieldtype": "Currency", "width": 125},
	]
	return columns, data
