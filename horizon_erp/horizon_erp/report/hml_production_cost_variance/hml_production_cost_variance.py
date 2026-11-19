"""HML Production Cost Variance - actual vs standard (BOM) cost per Work Order.

Standard = BOM unit cost at the time of the report x produced qty
	(material = raw_material_cost, operating = operating_cost).
Actual   = Manufacture Stock Entries of the WO:
	material = value of items consumed, operating = additional costs
	(operating + corrective / rework cost added by ERPNext).
Variance = actual - standard (positive = over standard cost).
"""

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.constants import COMPANY


def execute(filters=None):
	filters = frappe._dict(filters or {})
	wos = frappe.get_all(
		"Work Order",
		filters={"company": COMPANY, "docstatus": 1, "produced_qty": (">", 0)},
		fields=["name", "production_item", "bom_no", "produced_qty", "hml_has_rework", "corrective_operation_cost", "actual_end_date"],
		order_by="actual_end_date desc",
	)
	data = []
	for wo in wos:
		bom = frappe.db.get_value("BOM", wo.bom_no, ["raw_material_cost", "operating_cost", "quantity"], as_dict=True)
		per = flt(wo.produced_qty) / flt(bom.quantity or 1)
		std_mat = flt(bom.raw_material_cost) * per
		std_op = flt(bom.operating_cost) * per
		act = frappe.db.sql(
			"""select
				sum(case when sed.s_warehouse is not null and ifnull(sed.is_finished_item, 0) = 0 then sed.amount else 0 end) material,
				sum(case when sed.is_finished_item = 1 then sed.amount else 0 end) fg_value
			from `tabStock Entry Detail` sed join `tabStock Entry` se on se.name = sed.parent
			where se.work_order = %s and se.purpose = 'Manufacture' and se.docstatus = 1""",
			wo.name,
			as_dict=True,
		)[0]
		act_mat = flt(act.material)
		act_total = flt(act.fg_value)
		act_op = act_total - act_mat
		std_total = std_mat + std_op
		data.append(
			{
				"work_order": wo.name,
				"item_code": wo.production_item,
				"produced_qty": wo.produced_qty,
				"completed_on": wo.actual_end_date,
				"std_material": std_mat,
				"act_material": act_mat,
				"std_operating": std_op,
				"act_operating": act_op,
				"rework_cost": flt(wo.corrective_operation_cost),
				"std_total": std_total,
				"act_total": act_total,
				"variance": act_total - std_total,
				"variance_pct": (act_total - std_total) / std_total * 100 if std_total else None,
				"had_rework": wo.hml_has_rework,
			}
		)
	columns = [
		{"label": _("Work Order"), "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 150},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Produced"), "fieldname": "produced_qty", "fieldtype": "Float", "width": 80},
		{"label": _("Completed"), "fieldname": "completed_on", "fieldtype": "Datetime", "width": 140},
		{"label": _("Std Material"), "fieldname": "std_material", "fieldtype": "Currency", "width": 115},
		{"label": _("Actual Material"), "fieldname": "act_material", "fieldtype": "Currency", "width": 120},
		{"label": _("Std Operating"), "fieldname": "std_operating", "fieldtype": "Currency", "width": 115},
		{"label": _("Actual Operating"), "fieldname": "act_operating", "fieldtype": "Currency", "width": 125},
		{"label": _("of which Rework"), "fieldname": "rework_cost", "fieldtype": "Currency", "width": 115},
		{"label": _("Std Total"), "fieldname": "std_total", "fieldtype": "Currency", "width": 115},
		{"label": _("Actual Total"), "fieldname": "act_total", "fieldtype": "Currency", "width": 115},
		{"label": _("Variance"), "fieldname": "variance", "fieldtype": "Currency", "width": 110},
		{"label": _("Variance %"), "fieldname": "variance_pct", "fieldtype": "Percent", "width": 95},
		{"label": _("Had Rework"), "fieldname": "had_rework", "fieldtype": "Check", "width": 85},
	]
	return columns, data
