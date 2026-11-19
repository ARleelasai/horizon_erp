"""Reorder jobs for Horizon purchased items.

* recalculate_reorder_levels (daily): writes Item.hml_avg_daily_usage,
  hml_safety_stock_qty, hml_reorder_point and the Item Reorder row for the
  item's default warehouse (see horizon_erp.planning for the formula).
* create_reorder_material_requests (hourly): for every HML Item Reorder row
  whose projected qty is below the reorder level and that has no open
  auto-request, raise a Material Request. Items are grouped into ONE request
  per default supplier, so procurement turns each request into one PO.
"""

import frappe
from frappe.utils import add_days, add_months, cint, flt, getdate, nowdate

from horizon_erp.constants import COMPANY
from horizon_erp.planning import monthly_demand, reorder_parameters


def hml_purchase_items():
	return frappe.db.sql_list(
		"""select i.name from `tabItem` i
		join `tabItem Default` d on d.parent = i.name and d.company = %s
		where i.disabled = 0 and i.is_purchase_item = 1 and i.is_stock_item = 1""",
		COMPANY,
	)


def recalculate_reorder_levels(on_date=None):
	on_date = getdate(on_date or nowdate())
	items = hml_purchase_items()
	history = monthly_demand(items, add_months(on_date, -24), on_date)
	updated = []
	for code in items:
		p = reorder_parameters(code, on_date, history)
		frappe.db.set_value(
			"Item",
			code,
			{
				"hml_avg_daily_usage": p.avg_daily_usage,
				"hml_safety_stock_qty": p.safety_stock,
				"hml_reorder_point": p.reorder_point,
				"safety_stock": p.safety_stock,
			},
			update_modified=False,
		)
		warehouse = frappe.db.get_value("Item Default", {"parent": code, "company": COMPANY}, "default_warehouse")
		if not warehouse or not p.reorder_point:
			continue
		row = frappe.db.get_value("Item Reorder", {"parent": code, "warehouse": warehouse}, "name")
		values = {
			"warehouse_reorder_level": p.reorder_point,
			"warehouse_reorder_qty": p.reorder_qty,
			"material_request_type": "Purchase",
			"warehouse_group": None,
		}
		if row:
			frappe.db.set_value("Item Reorder", row, values, update_modified=False)
		else:
			item = frappe.get_doc("Item", code)
			item.append("reorder_levels", {"warehouse": warehouse, **values})
			item.flags.ignore_permissions = True
			item.save()
		updated.append((code, p.reorder_point, p.reorder_qty))
	return updated


def items_below_reorder():
	rows = frappe.db.sql(
		"""
		select r.parent as item_code, r.warehouse, r.warehouse_reorder_level as level,
			r.warehouse_reorder_qty as reorder_qty, ifnull(b.projected_qty, 0) as projected_qty,
			ifnull(b.actual_qty, 0) as actual_qty
		from `tabItem Reorder` r
		join `tabWarehouse` w on w.name = r.warehouse and w.company = %s
		left join `tabBin` b on b.item_code = r.parent and b.warehouse = r.warehouse
		where r.warehouse_reorder_level > 0
		""",
		COMPANY,
		as_dict=True,
	)
	return [r for r in rows if flt(r.projected_qty) < flt(r.level)]


def create_reorder_material_requests(on_date=None):
	on_date = getdate(on_date or nowdate())
	by_supplier = {}
	for r in items_below_reorder():
		open_mr = frappe.db.sql(
			"""select mr.name from `tabMaterial Request` mr
			join `tabMaterial Request Item` mri on mri.parent = mr.name
			where mr.company = %s and mr.docstatus < 2 and mr.status not in ('Stopped', 'Cancelled', 'Ordered', 'Received')
				and mr.hml_auto_reorder = 1 and mri.item_code = %s and mri.warehouse = %s limit 1""",
			(COMPANY, r.item_code, r.warehouse),
		)
		if open_mr:
			continue
		supplier = frappe.db.get_value("Item Default", {"parent": r.item_code, "company": COMPANY}, "default_supplier")
		qty = max(flt(r.reorder_qty), flt(r.level) - flt(r.projected_qty))
		by_supplier.setdefault(supplier or "", []).append((r, qty))

	created = []
	for supplier, rows in by_supplier.items():
		lead = max(cint(frappe.get_cached_value("Item", r.item_code, "lead_time_days")) for r, _q in rows)
		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"company": COMPANY,
				"material_request_type": "Purchase",
				"transaction_date": on_date,
				"schedule_date": add_days(on_date, lead or 7),
				"hml_supplier": supplier or None,
				"hml_auto_reorder": 1,
				"items": [
					{
						"item_code": r.item_code,
						"qty": qty,
						"warehouse": r.warehouse,
						"schedule_date": add_days(on_date, cint(frappe.get_cached_value("Item", r.item_code, "lead_time_days")) or 7),
					}
					for r, qty in rows
				],
			}
		)
		mr.flags.ignore_permissions = True
		mr.insert()
		mr.submit()
		created.append({"material_request": mr.name, "supplier": supplier, "items": [r.item_code for r, _q in rows]})
	if created:
		frappe.logger("horizon").info(f"reorder material requests: {created}")
	return created
