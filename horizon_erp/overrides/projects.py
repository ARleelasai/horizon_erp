"""Project costing, milestone billing and timesheet overtime (Horizon only).

Project cost = labour (timesheet costing) + material (stock issued to the
project + purchase invoices booked to it) + overhead (Project.hml_overhead_pct
of direct cost). Margin % = (earned - cost) / earned, where earned = milestone
billing to date; budgeted margin uses Estimated Cost vs contract value.

Milestone billing: when a Task with is_milestone + Billing % is set to
Completed, a Sales Invoice is raised against the project's Sales Order line
for that share of the contract. The invoice records the material / labour /
overhead incurred to date, so the customer and Finance see what the
milestone covers.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from horizon_erp.constants import COMPANY, is_hml

OVERTIME_AFTER_HOURS = 8


# ------------------------------------------------------------------ project


def project_costs(project):
	p = frappe.db.get_value(
		"Project",
		project,
		["total_costing_amount", "total_consumed_material_cost", "total_purchase_cost", "hml_overhead_pct", "sales_order",
			"estimated_costing"],
		as_dict=True,
	)
	labour = flt(p.total_costing_amount)
	material = flt(p.total_consumed_material_cost) + flt(p.total_purchase_cost)
	overhead = (labour + material) * flt(p.hml_overhead_pct) / 100
	return frappe._dict(labour=labour, material=material, overhead=overhead, total=labour + material + overhead, project=p)


def update_project_costing(doc, method=None):
	if not is_hml(doc):
		return
	costs = project_costs(doc.name) if not doc.is_new() else None
	contract = flt(frappe.db.get_value("Sales Order", doc.sales_order, "base_net_total")) if doc.sales_order else 0
	billed = flt(
		frappe.db.sql(
			"select sum(base_net_total) from `tabSales Invoice` where project = %s and docstatus = 1 and is_return = 0", doc.name
		)[0][0]
	) if not doc.is_new() else 0
	values = {"hml_contract_value": contract, "hml_billed_amount": billed}
	if costs:
		values.update(
			{
				"hml_labour_cost": costs.labour,
				"hml_material_cost": costs.material,
				"hml_overhead_cost": costs.overhead,
				"hml_total_cost": costs.total,
				"hml_margin_pct": (billed - costs.total) / billed * 100 if billed else 0,
			}
		)
	est = flt(doc.estimated_costing) * (1 + flt(doc.hml_overhead_pct) / 100)
	values["hml_budget_margin_pct"] = (contract - est) / contract * 100 if contract else 0
	for k, v in values.items():
		doc.set(k, v)


def refresh_all_projects():
	"""Daily: timesheets and stock issues change cost without touching the Project."""
	for name in frappe.get_all("Project", filters={"company": COMPANY, "status": "Open"}, pluck="name"):
		doc = frappe.get_doc("Project", name)
		update_project_costing(doc)
		doc.db_update()


# -------------------------------------------------------------- milestones


def validate_task(doc, method=None):
	if not doc.project or frappe.db.get_value("Project", doc.project, "company") != COMPANY:
		return
	if doc.is_milestone and flt(doc.hml_billing_pct):
		contract = flt(frappe.db.get_value("Project", doc.project, "hml_contract_value"))
		doc.hml_billing_amount = contract * flt(doc.hml_billing_pct) / 100


def on_update_task(doc, method=None):
	if doc.status != "Completed" or not doc.is_milestone or not flt(doc.hml_billing_pct) or doc.hml_milestone_invoice:
		return
	if frappe.db.get_value("Project", doc.project, "company") != COMPANY:
		return
	invoice = create_milestone_invoice(doc)
	doc.db_set("hml_milestone_invoice", invoice, update_modified=False)


def create_milestone_invoice(task):
	project = frappe.get_doc("Project", task.project)
	if not project.sales_order:
		frappe.throw(_("Project {0} has no Sales Order; milestone billing needs one.").format(project.name))
	so = frappe.get_doc("Sales Order", project.sales_order)
	costs = project_costs(project.name)
	share = flt(task.hml_billing_pct) / 100
	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": so.company,
			"customer": so.customer,
			"project": project.name,
			"posting_date": getdate(task.completed_on or nowdate()),
			"set_posting_time": 1,
			"company_address": so.company_address,
			"customer_address": so.customer_address,
			"selling_price_list": so.selling_price_list,
			"update_stock": 0,
			"hml_project_milestone": task.name,
			"hml_material_cost": costs.material,
			"hml_labour_cost": costs.labour,
			"hml_overhead_cost": costs.overhead,
			"remarks": _(
				"Milestone '{0}' ({1}% of contract). Cost incurred to date: material Rs {2:,.0f}, labour Rs {3:,.0f}, overhead Rs {4:,.0f}."
			).format(task.subject, task.hml_billing_pct, costs.material, costs.labour, costs.overhead),
			"items": [
				{
					"item_code": row.item_code,
					"qty": flt(row.qty) * share,
					"rate": row.rate,
					"price_list_rate": row.price_list_rate,
					"discount_percentage": row.discount_percentage,
					"sales_order": so.name,
					"so_detail": row.name,
					"project": project.name,
					"description": f"{row.description} - milestone: {task.subject}",
				}
				for row in so.items
			],
			"taxes_and_charges": so.taxes_and_charges,
		}
	)
	si.flags.ignore_permissions = True
	si.set_missing_values()
	si.insert()
	si.submit()
	return si.name


# --------------------------------------------------------------- timesheets


def validate_timesheet(doc, method=None):
	if not is_hml(doc) or not doc.employee:
		return
	per_day = {}
	for row in doc.time_logs:
		if row.from_time:
			d = getdate(row.from_time)
			per_day[d] = per_day.get(d, 0) + flt(row.hours)
	overtime = 0
	for d, hours in per_day.items():
		other = flt(
			frappe.db.sql(
				"""select sum(tl.hours) from `tabTimesheet Detail` tl join `tabTimesheet` ts on ts.name = tl.parent
				where ts.employee = %s and ts.docstatus < 2 and ts.name != %s and date(tl.from_time) = %s""",
				(doc.employee, doc.name or "", d),
			)[0][0]
		)
		overtime += max(hours + other - OVERTIME_AFTER_HOURS, 0) if hours + other > OVERTIME_AFTER_HOURS else 0
	doc.hml_overtime_hours = round(overtime, 2)
	doc.hml_has_overtime = 1 if overtime > 0 else 0
