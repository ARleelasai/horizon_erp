"""Install / migrate hooks: roles and custom fields (idempotent)."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from horizon_erp.constants import BRANCH_DELHI, BRANCH_MUMBAI, HML_ROLES


def after_install():
	after_migrate()


def after_migrate():
	make_roles()
	make_custom_fields()
	make_location_dimension()
	from horizon_erp.setup.workflows import make_all

	make_all()
	from horizon_erp.setup import workspaces

	workspaces.make_all()


def make_roles():
	for role in HML_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)


def make_custom_fields():
	from horizon_erp.setup.custom_fields import get_custom_fields

	fields = get_custom_fields()
	for rows in fields.values():
		for row in rows:
			row.setdefault("module", "Horizon ERP")
	create_custom_fields(fields, update=True)


def make_location_dimension():
	"""Location accounting dimension, backed by the standard Branch doctype.

	Branch is used (not a new doctype, not Location) because Salary Slip and
	Payroll Entry already carry a `branch` Link, so payroll GL lands on the
	right location without extra mapping. ERPNext's Location doctype was
	avoided: Asset.location already means the physical spot of an asset.

	Field creation is DDL (implicit commit), which is why it lives in migrate
	and not in the seed transaction. The per-company default and the
	"mandatory for P&L" flag are set by the seed.
	"""
	for branch in (BRANCH_MUMBAI, BRANCH_DELHI):
		if not frappe.db.exists("Branch", branch):
			frappe.get_doc({"doctype": "Branch", "branch": branch}).insert(ignore_permissions=True)

	if frappe.db.exists("Accounting Dimension", {"document_type": "Branch"}):
		return

	from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
		make_dimension_in_accounting_doctypes,
	)

	frappe.flags.in_test = True  # makes after_insert build the fields synchronously
	try:
		dim = frappe.get_doc(
			{"doctype": "Accounting Dimension", "document_type": "Branch", "label": "Branch"}
		)
		dim.insert(ignore_permissions=True)
	finally:
		frappe.flags.in_test = False
	if not frappe.get_meta("GL Entry").has_field("branch"):
		make_dimension_in_accounting_doctypes(doc=dim)


def sync_app_files():
	"""Dev helper: reload every DocType/Report/Workspace/etc. JSON in this app.

	bench --site FSM.local execute horizon_erp.setup.install.sync_app_files
	Avoids a full `bench migrate` on a site with many apps.
	"""
	import os

	from frappe.modules.import_file import import_file_by_path

	module_path = frappe.get_app_path("horizon_erp", "horizon_erp")
	order = ["doctype", "report", "page", "print_format", "workspace", "number_card", "dashboard_chart", "dashboard"]
	for folder in order:
		base = os.path.join(module_path, folder)
		if not os.path.isdir(base):
			continue
		names = sorted(os.listdir(base))
		if folder == "doctype":
			# child tables first so parents can link to them
			names.sort(key=lambda n: 0 if _is_child(os.path.join(base, n, f"{n}.json")) else 1)
		for name in names:
			path = os.path.join(base, name, f"{name}.json")
			if os.path.exists(path):
				import_file_by_path(path, force=True)
				print(f"synced {folder}/{name}")
	frappe.clear_cache()
	after_migrate()


def _is_child(path):
	import json

	try:
		return json.load(open(path)).get("istable")
	except Exception:
		return False
