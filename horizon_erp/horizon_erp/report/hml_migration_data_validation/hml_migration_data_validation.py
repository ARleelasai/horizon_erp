"""HML Migration Data Validation - what the legacy system let through.

Summary per entity and issue: how many records, how many the rules fixed
automatically, how many need a person, and which rule decided. Detail view
lists every record with original and corrected value.
"""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if filters.view == "Detail":
		cond = {}
		if filters.entity:
			cond["entity"] = filters.entity
		if filters.status:
			cond["status"] = filters.status
		rows = frappe.get_all("Migration Staging Row", filters=cond,
			fields=["name", "entity", "legacy_id", "legacy_name", "issue", "status", "original_value", "corrected_value", "amount", "qty", "rule"],
			order_by="entity, status, legacy_id")
		cols = [
			{"label": _("Row"), "fieldname": "name", "fieldtype": "Link", "options": "Migration Staging Row", "width": 110},
			{"label": _("Entity"), "fieldname": "entity", "fieldtype": "Data", "width": 120},
			{"label": _("Legacy ID"), "fieldname": "legacy_id", "fieldtype": "Data", "width": 110},
			{"label": _("Name"), "fieldname": "legacy_name", "fieldtype": "Data", "width": 180},
			{"label": _("Issue"), "fieldname": "issue", "fieldtype": "Data", "width": 170},
			{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
			{"label": _("Original"), "fieldname": "original_value", "fieldtype": "Data", "width": 160},
			{"label": _("Corrected"), "fieldname": "corrected_value", "fieldtype": "Data", "width": 160},
			{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 110},
			{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 70},
			{"label": _("Rule"), "fieldname": "rule", "fieldtype": "Data", "width": 360},
		]
		return cols, rows
	rows = frappe.db.sql(
		"""select entity, issue, count(*) total, sum(status = 'Auto-fixed') auto_fixed, sum(status = 'Needs Review') review,
			sum(status in ('Approved for Import', 'Imported')) imported, sum(status = 'Rejected') rejected, sum(status = 'Pending') pending
		from `tabMigration Staging Row` group by entity, issue order by entity, issue""",
		as_dict=True,
	)
	prevention = {
		"Invalid GSTIN": "India Compliance GSTIN format + check digit + state code; Horizon PAN-in-GSTIN check",
		"GSTIN State Mismatch": "India Compliance address state vs GSTIN state code",
		"Negative Stock": "Stock Settings: negative stock disabled; stock receipt only via inspected GRN",
		"Purchase Invoice Without PO": "Horizon: stock items must be billed against a PO / receipt",
	}
	for r in rows:
		r["prevented_by"] = prevention.get(r.issue)
	cols = [
		{"label": _("Entity"), "fieldname": "entity", "fieldtype": "Data", "width": 130},
		{"label": _("Issue"), "fieldname": "issue", "fieldtype": "Data", "width": 200},
		{"label": _("Records"), "fieldname": "total", "fieldtype": "Int", "width": 80},
		{"label": _("Auto-fixed"), "fieldname": "auto_fixed", "fieldtype": "Int", "width": 90},
		{"label": _("Needs Review"), "fieldname": "review", "fieldtype": "Int", "width": 100},
		{"label": _("Imported"), "fieldname": "imported", "fieldtype": "Int", "width": 80},
		{"label": _("Rejected"), "fieldname": "rejected", "fieldtype": "Int", "width": 80},
		{"label": _("Pending"), "fieldname": "pending", "fieldtype": "Int", "width": 75},
		{"label": _("Now Prevented By"), "fieldname": "prevented_by", "fieldtype": "Data", "width": 420},
	]
	return cols, rows
