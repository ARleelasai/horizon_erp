"""HML Asset Register.

Original cost, accumulated depreciation (opening + posted), net book value,
last maintenance date, maintenance cost YTD and in the last 12 months, and
maintenance as % of NBV. Assets whose 12-month maintenance exceeds 15 % of
NBV are flagged as replacement candidates (and Asset.hml_replacement_flag is
updated, so the flag is visible on the asset itself).
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from horizon_erp.constants import COMPANY

REPLACEMENT_THRESHOLD = 15.0


def execute(filters=None):
	filters = frappe._dict(filters or {})
	today = getdate(filters.as_on_date or nowdate())
	fy_start = getdate("2026-04-01") if today >= getdate("2026-04-01") else getdate("2025-04-01")
	assets = frappe.get_all(
		"Asset",
		filters={"company": COMPANY, "docstatus": 1, **({} if filters.include_disposed else {"status": ("not in", ["Sold", "Scrapped"])})},
		fields=["name", "asset_name", "asset_category", "status", "purchase_date", "gross_purchase_amount", "opening_accumulated_depreciation",
			"value_after_depreciation", "hml_production_line", "insured_value", "insurance_end_date", "disposal_date"],
		order_by="asset_category, gross_purchase_amount desc",
	)
	data = []
	for a in assets:
		posted = flt(
			frappe.db.sql(
				"""select sum(ds.depreciation_amount) from `tabDepreciation Schedule` ds
				join `tabAsset Depreciation Schedule` ads on ads.name = ds.parent
				where ads.asset = %s and ads.docstatus = 1 and ifnull(ds.journal_entry, '') != ''""",
				a.name,
			)[0][0]
		)
		accumulated = flt(a.opening_accumulated_depreciation) + posted
		nbv = flt(a.gross_purchase_amount) - accumulated
		mj = frappe.db.sql(
			"""select max(job_date), sum(case when job_date >= %s then total_cost else 0 end),
				sum(case when job_date >= %s then total_cost else 0 end), count(*)
			from `tabMaintenance Job` where asset = %s and docstatus = 1""",
			(fy_start, add_days(today, -365), a.name),
		)[0]
		last, ytd, last12, jobs = mj
		pct = flt(last12) / nbv * 100 if nbv > 0 else (100 if flt(last12) else 0)
		flag = 1 if pct > REPLACEMENT_THRESHOLD else 0
		if a.status not in ("Sold", "Scrapped"):
			frappe.db.set_value("Asset", a.name, "hml_replacement_flag", flag, update_modified=False)
		data.append(
			{
				"asset": a.name,
				"asset_name": a.asset_name,
				"category": a.asset_category,
				"line": a.hml_production_line,
				"status": a.status,
				"purchase_date": a.purchase_date,
				"cost": a.gross_purchase_amount,
				"accumulated": accumulated,
				"nbv": nbv,
				"last_maintenance": last,
				"maintenance_jobs": jobs,
				"maintenance_ytd": flt(ytd),
				"maintenance_12m_pct": round(pct, 1),
				"replace": flag,
				"insurance_end": a.insurance_end_date,
			}
		)
	columns = [
		{"label": _("Asset"), "fieldname": "asset", "fieldtype": "Link", "options": "Asset", "width": 140},
		{"label": _("Name"), "fieldname": "asset_name", "fieldtype": "Data", "width": 200},
		{"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 170},
		{"label": _("Line"), "fieldname": "line", "fieldtype": "Data", "width": 95},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Purchased"), "fieldname": "purchase_date", "fieldtype": "Date", "width": 95},
		{"label": _("Original Cost"), "fieldname": "cost", "fieldtype": "Currency", "width": 125},
		{"label": _("Accumulated Depreciation"), "fieldname": "accumulated", "fieldtype": "Currency", "width": 140},
		{"label": _("Net Book Value"), "fieldname": "nbv", "fieldtype": "Currency", "width": 125},
		{"label": _("Last Maintenance"), "fieldname": "last_maintenance", "fieldtype": "Date", "width": 115},
		{"label": _("Jobs"), "fieldname": "maintenance_jobs", "fieldtype": "Int", "width": 55},
		{"label": _("Maintenance YTD"), "fieldname": "maintenance_ytd", "fieldtype": "Currency", "width": 120},
		{"label": _("Maint. 12 m % of NBV"), "fieldname": "maintenance_12m_pct", "fieldtype": "Percent", "width": 125},
		{"label": _("Replacement Candidate"), "fieldname": "replace", "fieldtype": "Check", "width": 110},
		{"label": _("Insurance Ends"), "fieldname": "insurance_end", "fieldtype": "Date", "width": 105},
	]
	summary = [
		{"label": _("Gross block"), "value": sum(flt(d["cost"]) for d in data), "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Net block"), "value": sum(flt(d["nbv"]) for d in data), "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Maintenance YTD"), "value": sum(flt(d["maintenance_ytd"]) for d in data), "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Replacement candidates"), "value": len([d for d in data if d["replace"]]), "indicator": "Red"},
	]
	return columns, data, None, None, summary
