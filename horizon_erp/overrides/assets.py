"""Asset retirement for Horizon.

retire_asset() is the single entry point (button on Asset, used by the seed):
  * "Sell"  -> Sales Invoice for the salvage value; ERPNext books disposal,
               reverses accumulated depreciation and posts gain / loss.
  * "Scrap" -> ERPNext scrap_asset: writes off NBV to the disposal account.
The disposal date and reason are kept on the asset for the register.
"""

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def retire_asset(asset, method, disposal_date, reason, salvage_value=0, customer=None):
	frappe.has_permission("Asset", "write", asset, throw=True)
	doc = frappe.get_doc("Asset", asset)
	if doc.docstatus != 1 or doc.status in ("Sold", "Scrapped"):
		frappe.throw(_("Only an active, submitted asset can be retired."))
	doc.db_set("hml_retirement_reason", reason)
	if method == "Scrap":
		from erpnext.assets.doctype.asset.depreciation import scrap_asset

		scrap_asset(asset, disposal_date)
		return {"method": "Scrap", "journal_entry": frappe.db.get_value("Asset", asset, "journal_entry_for_scrap")}
	if not customer:
		frappe.throw(_("Select the buyer (customer) for a sale."))
	from erpnext.assets.doctype.asset.asset import make_sales_invoice

	si = make_sales_invoice(asset, doc.item_code, doc.company)
	si.customer = customer
	si.company_address = frappe.db.get_value(
		"Address", {"is_your_company_address": 1, "gstin": frappe.db.get_value("Company", doc.company, "gstin")}
	)
	si.posting_date = disposal_date
	si.set_posting_time = 1
	si.update_stock = 0
	for row in si.items:
		row.rate = flt(salvage_value)
	si.flags.ignore_permissions = True
	si.set_missing_values()
	si.insert()
	si.submit()
	return {"method": "Sell", "sales_invoice": si.name}
