"""Inventory background jobs for Horizon.

Cycle counting replaces the quarterly full count:
* Items carry an ABC class (Item.hml_abc_class): A counted every 30 days,
  B every 60, C every 90.
* Weekly job `create_cycle_count_drafts` builds one DRAFT Stock Reconciliation
  per HML warehouse with the items that are due, pre-filled with the system
  quantity. The storekeeper overwrites qty with the physical count and submits.
* On submit, `on_stock_reco_submit` stamps Item.hml_last_counted_on, and the
  variance posts to Stock Adjustment automatically (standard ERPNext).

Drafts are never auto-submitted: a count that nobody performed must not
silently "confirm" the book quantity.
"""

import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from horizon_erp.constants import COMPANY, is_hml

COUNT_INTERVAL_DAYS = {"A": 30, "B": 60, "C": 90}


def due_items(warehouse, today=None):
	today = getdate(today or nowdate())
	rows = frappe.db.sql(
		"""
		select b.item_code, b.actual_qty, b.valuation_rate,
			i.hml_abc_class, i.hml_last_counted_on
		from `tabBin` b
		join `tabItem` i on i.name = b.item_code
		where b.warehouse = %s and b.actual_qty > 0
			and i.disabled = 0 and i.has_batch_no = 0 and i.has_serial_no = 0
		""",
		warehouse,
		as_dict=True,
	)
	due = []
	for r in rows:
		interval = COUNT_INTERVAL_DAYS.get(r.hml_abc_class or "C", 90)
		last = getdate(r.hml_last_counted_on) if r.hml_last_counted_on else None
		if not last or add_days(last, interval) <= today:
			due.append(r)
	return due


def create_cycle_count_drafts(today=None):
	"""Weekly: one draft Stock Reconciliation per warehouse with due items."""
	created = []
	warehouses = frappe.get_all(
		"Warehouse", filters={"company": COMPANY, "is_group": 0, "disabled": 0, "warehouse_type": ("!=", "Transit")}, pluck="name"
	)
	for warehouse in warehouses:
		if frappe.db.exists(
			"Stock Reconciliation",
			{"company": COMPANY, "docstatus": 0, "hml_cycle_count_warehouse": warehouse},
		):
			continue  # previous count not finished; do not stack drafts
		items = due_items(warehouse, today)
		if not items:
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Stock Reconciliation",
				"company": COMPANY,
				"purpose": "Stock Reconciliation",
				"hml_cycle_count_warehouse": warehouse,
				"items": [
					{
						"item_code": r.item_code,
						"warehouse": warehouse,
						"qty": flt(r.actual_qty),
						"valuation_rate": flt(r.valuation_rate),
					}
					for r in items
				],
			}
		)
		# ERPNext drops rows whose qty is unchanged during validate, and the
		# draft is pre-filled with book qty, so the draft is saved unvalidated.
		# Validation runs in full when the counter submits.
		doc.flags.ignore_validate = True
		doc.insert(ignore_permissions=True)
		created.append(doc.name)
	if created:
		frappe.logger("horizon").info(f"cycle count drafts: {created}")
	return created


def before_stock_reco_validate(doc, method=None):
	"""Remember every counted item before ERPNext removes no-change rows."""
	if is_hml(doc):
		doc.flags.hml_counted_items = list({d.item_code for d in doc.items})


def on_stock_reco_submit(doc, method=None):
	if not is_hml(doc):
		return
	items = doc.flags.hml_counted_items or list({d.item_code for d in doc.items})
	if items:
		frappe.db.set_value(
			"Item",
			{"name": ("in", items)},
			"hml_last_counted_on",
			doc.posting_date,
			update_modified=False,
		)
