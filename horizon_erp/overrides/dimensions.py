"""Fill the Location (Branch) accounting dimension on every HML document.

Branch is mandatory for P&L accounts in HML (decision D-01), but ERPNext only
applies the dimension default in the browser. Server-created documents
(scheduler jobs, API calls, payroll, stock reconciliations) would fail GL
validation. This hook, wired to "*" before_validate, sets it server-side:

1. Header: Delhi company address or any Delhi warehouse -> DC Delhi,
   otherwise HQ Mumbai.
2. Child rows that carry a `branch` field: the row's own warehouse decides,
   falling back to the header value.

A value the user typed is never overwritten.
"""

import frappe

from horizon_erp.constants import (
	ADDRESS_DELHI,
	BRANCH_DELHI,
	BRANCH_MUMBAI,
	COMPANY,
	WH_DELHI,
)

HEADER_WAREHOUSE_FIELDS = ("set_warehouse", "set_from_warehouse", "set_target_warehouse", "from_warehouse", "to_warehouse")
ROW_WAREHOUSE_FIELDS = ("warehouse", "s_warehouse", "t_warehouse", "target_warehouse", "source_warehouse")


def _delhi_warehouses():
	cache = getattr(frappe.local, "hml_delhi_wh", None)
	if cache is None:
		bounds = frappe.db.get_value("Warehouse", WH_DELHI, ["lft", "rgt"], as_dict=True)
		cache = set()
		if bounds:
			cache = set(
				frappe.get_all(
					"Warehouse", filters={"lft": (">=", bounds.lft), "rgt": ("<=", bounds.rgt)}, pluck="name"
				)
			)
		frappe.local.hml_delhi_wh = cache
	return cache


def branch_for_warehouse(warehouse):
	if not warehouse:
		return None
	return BRANCH_DELHI if warehouse in _delhi_warehouses() else BRANCH_MUMBAI


def header_branch(doc):
	# Sales docs carry our GSTIN in company_address, purchase docs in billing_address
	if ADDRESS_DELHI in (doc.get("company_address"), doc.get("billing_address")):
		return BRANCH_DELHI
	for f in HEADER_WAREHOUSE_FIELDS:
		if doc.get(f):
			return branch_for_warehouse(doc.get(f))
	for table in doc.meta.get_table_fields():
		for row in doc.get(table.fieldname) or []:
			for f in ROW_WAREHOUSE_FIELDS:
				if row.get(f):
					return branch_for_warehouse(row.get(f))
	return BRANCH_MUMBAI


# HRMS uses `branch` on these as an employee filter, not only as a dimension:
# a defaulted HQ Mumbai would silently drop Delhi staff from the payroll run.
SKIP_DOCTYPES = {"Payroll Entry", "Employee", "Salary Structure Assignment"}


def _dimension_doctypes():
	cache = getattr(frappe.local, "hml_dimension_doctypes", None)
	if cache is None:
		from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_doctypes_with_dimensions

		cache = set(get_doctypes_with_dimensions())
		frappe.local.hml_dimension_doctypes = cache
	return cache


def set_branch(doc, method=None):
	if doc.get("company") != COMPANY or doc.meta.istable:
		return
	if doc.doctype in SKIP_DOCTYPES or doc.doctype not in _dimension_doctypes():
		return
	if frappe.flags.in_install or frappe.flags.in_migrate:
		return
	has_header = doc.meta.has_field("branch")
	branch = None
	if has_header:
		if not doc.get("branch"):
			doc.branch = header_branch(doc)
		branch = doc.branch
	for table in doc.meta.get_table_fields():
		child_meta = frappe.get_meta(table.options)
		if not child_meta.has_field("branch"):
			continue
		for row in doc.get(table.fieldname) or []:
			if row.get("branch"):
				continue
			row_branch = None
			for f in ROW_WAREHOUSE_FIELDS:
				if row.get(f):
					row_branch = branch_for_warehouse(row.get(f))
					break
			row.branch = row_branch or branch or header_branch(doc)
