"""Phase 2 - CRM & Selling for Horizon Manufacturing Ltd.

Pricing rules, leads, opportunities, quotations (incl. discount approvals,
a rejection and an expired quote), sales orders, pick lists, deliveries
(full, partial, branch transfer Mumbai -> Delhi) and auto-generated invoices.

Back-dated Aug-Nov 2026 so pipeline age, conversion velocity and "pending
delivery > 5 days" have realistic data on 19 Nov 2026.
"""

import zlib

import frappe
from erpnext.selling.doctype.quotation.quotation import _make_sales_order
from erpnext.selling.doctype.sales_order.sales_order import create_pick_list
from erpnext.stock.doctype.pick_list.pick_list import create_delivery_note
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, flt, getdate

from horizon_erp.constants import (
	ADDRESS_DELHI,
	ADDRESS_MUMBAI,
	BRANCH_DELHI,
	COMPANY,
	IG_COMPONENTS,
	IG_EQUIPMENT,
	IG_SPARES,
	WH_DELHI,
	WH_DELHI_FG,
	WH_FG,
	WH_MUMBAI,
	WH_TRANSIT,
)
from horizon_erp.setup.seed.phase1 import customer_name, user_email
from horizon_erp.setup.seed.utils import get_or_insert, log

SALES_EXEC = user_email("rohan.mehta")
SALES_MGR = user_email("sanjay.verma")
SALES_DIR = user_email("amit.kapoor")


def as_user(user):
	frappe.set_user(user)


def admin():
	frappe.set_user("Administrator")


# ------------------------------------------------------------- pricing rules

PRICING_RULES = [
	# title, groups, applicable_for, party value, discount, priority, min_qty, valid_from, valid_upto
	("HML Components Trade 2%", [IG_COMPONENTS], "", None, 2, 1, 0, None, None),
	("HML Premium Customer 5%", [IG_EQUIPMENT, IG_SPARES, IG_COMPONENTS], "Customer Group", "Premium", 5, 2, 0, None, None),
	("HML Bulk Order 51+ Units 7%", [IG_SPARES, IG_COMPONENTS], "", None, 7, 3, 51, None, None),
	("HML Q4 Spares Promotion 10%", [IG_SPARES], "", None, 10, 4, 0, "2027-01-01", "2027-03-31"),
]


def step_pricing_rules():
	"""Precedence (decision D-06): highest priority wins, no stacking.

	Seasonal 10 % (p4) > Bulk 7 % (p3) > Premium 5 % (p2) > Components 2 % (p1).
	Discount values rise with priority, so the winning rule is also the best
	one for the customer and the outcome is predictable for sales.
	"""
	for title, groups, applicable_for, party, discount, priority, min_qty, valid_from, valid_upto in PRICING_RULES:
		if frappe.db.exists("Pricing Rule", {"title": title}):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Pricing Rule",
				"title": title,
				"company": COMPANY,
				"apply_on": "Item Group",
				"item_groups": [{"item_group": g} for g in groups],
				"selling": 1,
				"buying": 0,
				"applicable_for": applicable_for,
				"customer_group": party if applicable_for == "Customer Group" else None,
				"rate_or_discount": "Discount Percentage",
				"discount_percentage": discount,
				"priority": str(priority),
				"min_qty": min_qty,
				"valid_from": valid_from or "2026-04-01",
				"valid_upto": valid_upto,
				"apply_multiple_pricing_rules": 0,
				"currency": "INR",
			}
		)
		doc.insert(ignore_permissions=True)
		log(f"+ Pricing Rule: {title}")


# ---------------------------------------------------------------------- CRM

LEADS = [
	# key, person, org, source, territory, interest, value, status, created
	("L1", "Vivek Kulkarni", "Shirdi Sugar Works", "Exhibition", "Maharashtra", "Equipment", 900000, "Open", "2026-07-18"),
	("L2", "Meenal Shah", "Surat Textile Machines", "Advertisement", "Gujarat", "Components", 250000, "Replied", "2026-09-02"),
	("L3", "Harpreet Gill", "Ludhiana Forgings", "Cold Calling", "Delhi NCR", "Spares", 120000, "Interested", "2026-10-21"),
	("L4", "Arun Prakash", "Hosur Auto Parts", "Reference", "Karnataka", "Equipment", 1850000, "Opportunity", "2026-08-11"),
	("L5", "Divya Rao", "Mysore Agro Mills", "Campaign", "Karnataka", "Spares", 60000, "Lead", "2026-11-12"),
	("L6", "Kunal Bhatia", "Faridabad Fabtech", "Walk In", "Delhi NCR", "Custom Project", 3200000, "Opportunity", "2026-09-25"),
	("L7", "Sameer Joshi", "Kolhapur Foundry", "Exhibition", "Maharashtra", "Components", 80000, "Do Not Contact", "2026-06-05"),
	("L8", "Ritu Agarwal", "Jaipur Cement Works", "Advertisement", "Delhi NCR", "Equipment", 700000, "Lost Quotation", "2026-05-20"),
]


def lead_name(key):
	org = next(l[2] for l in LEADS if l[0] == key)
	return frappe.db.get_value("Lead", {"company_name": org})


def step_leads():
	for key, person, org, source, territory, interest, value, status, created in LEADS:
		if lead_name(key):
			continue
		first, last = person.split(" ", 1)
		doc = frappe.get_doc(
			{
				"doctype": "Lead",
				"first_name": first,
				"last_name": last,
				"company_name": org,
				"email_id": f"{first.lower()}@{org.split()[0].lower()}.example.com",
				"mobile_no": f"+91 9{zlib.crc32(org.encode()) % 10**9:09d}",
				"source": source,
				"territory": territory,
				"company": COMPANY,
				"hml_product_interest": interest,
				"hml_estimated_value": value,
				"lead_owner": SALES_EXEC,
				"status": "Lead",
			}
		)
		doc.insert(ignore_permissions=True)
		if status != "Lead":
			frappe.db.set_value("Lead", doc.name, "status", status, update_modified=False)
		frappe.db.set_value("Lead", doc.name, {"creation": f"{created} 10:00:00", "modified": f"{created} 10:00:00"}, update_modified=False)
		log(f"+ Lead: {doc.name} {org} [{status}]")


OPPORTUNITIES = [
	# lead key, stage, amount, probability, opened, closing
	("L4", "Proposal/Price Quote", 1850000, 60, "2026-08-20", "2026-12-15"),
	("L6", "Needs Analysis", 3200000, 30, "2026-10-01", "2027-01-31"),
]


def step_opportunities():
	for key, stage, amount, prob, opened, closing in OPPORTUNITIES:
		lead = lead_name(key)
		if frappe.db.exists("Opportunity", {"party_name": lead}):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Opportunity",
				"opportunity_from": "Lead",
				"party_name": lead,
				"company": COMPANY,
				"transaction_date": opened,
				"opportunity_type": "Sales",
				"sales_stage": stage,
				"opportunity_amount": amount,
				"probability": prob,
				"expected_closing": closing,
				"opportunity_owner": SALES_EXEC,
				"currency": "INR",
			}
		)
		doc.insert(ignore_permissions=True)
		log(f"+ Opportunity: {doc.name} ({stage})")


# --------------------------------------------------------------- quotations

QUOTES = {
	# key: customer key, date, address, price list, items[(code, qty, extra_discount%)], reason, flow
	#   flow: submit | approve | reject | expire | draft
	"Q1": ("apex", "2026-08-12", ADDRESS_MUMBAI, "HML Standard Selling", [("CX-200", 2, 0)], None, "submit"),
	"Q2": ("northern", "2026-09-04", ADDRESS_DELHI, "HML North Region Selling",
		[("SP-SEAL-KIT-HX", 55, 0), ("SP-FILTER-RET", 20, 0)], None, "submit"),
	"Q3": ("gujarat", "2026-09-28", ADDRESS_MUMBAI, "HML Standard Selling", [("HX-500", 1, 13)],
		"Competing with an imported press quoted at Rs 3.9 L landed. Customer will place 3 more units in FY27 if we win this one.", "approve"),
	"Q4": ("deccan", "2026-10-06", ADDRESS_MUMBAI, "HML Standard Selling",
		[("CMP-CYL-100", 4, 22), ("CMP-PUMP-GP20", 4, 22)], "Customer asked to match a local fabricator's price.", "reject"),
	"Q5": ("sahyadri", "2026-08-03", ADDRESS_MUMBAI, "HML Standard Selling", [("CX-200", 1, 0), ("SP-BELT-600-10M", 2, 0)], None, "expire"),
	"Q6": ("capital", "2026-11-14", ADDRESS_DELHI, "HML North Region Selling", [("SP-ROLLER-SET10", 8, 0), ("CMP-MOTOR-2HP", 6, 5)],
		"Distributor margin on first stocking order.", "draft"),
	"Q8": ("gujarat", "2026-11-16", ADDRESS_MUMBAI, "HML Standard Selling", [("SP-SEAL-KIT-HX", 20, 0), ("SP-HOSE-KIT", 10, 0)], None, "submit"),
	"Q9": ("apex", "2026-10-26", ADDRESS_MUMBAI, "HML Standard Selling", [("HX-500", 2, 0)], None, "submit"),
	"Q7": ("abc", "2026-11-06", ADDRESS_MUMBAI, "HML Standard Selling", [("SP-HOSE-KIT", 12, 0), ("SP-FILTER-RET", 30, 0)], None, "submit"),
}


def quote_name(key):
	return frappe.db.get_value("Quotation", {"title": f"{key} - HML seed", "docstatus": ("<", 2)})


def step_quotations():
	for key, (cust_key, date, address, price_list, items, reason, flow) in QUOTES.items():
		if quote_name(key):
			continue
		as_user(SALES_EXEC)
		doc = frappe.get_doc(
			{
				"doctype": "Quotation",
				"title": f"{key} - HML seed",
				"quotation_to": "Customer",
				"party_name": customer_name(cust_key),
				"company": COMPANY,
				"transaction_date": date,
				"company_address": address,
				"selling_price_list": price_list,
				"hml_discount_reason": reason,
				"items": [{"item_code": code, "qty": qty} for code, qty, _x in items],
			}
		)
		doc.insert()
		# manual discount on top of pricing rules: a header "special discount"
		# (row discounts are re-derived from Pricing Rules on every save)
		extra = max(x for _c, _q, x in items)
		if extra:
			doc.apply_discount_on = "Net Total"
			doc.additional_discount_percentage = extra
			doc.save()
		log(f"+ Quotation {doc.name} [{key}] eff {doc.hml_effective_discount_pct}% approval={doc.hml_needs_discount_approval}")

		if flow in ("submit", "expire"):
			apply_workflow(doc, "Submit")
		elif flow in ("approve", "reject"):
			apply_workflow(doc, "Request Discount Approval")
			approver = SALES_MGR if flow == "approve" else SALES_DIR
			as_user(approver)
			doc.reload()
			doc.add_comment(
				"Comment",
				"Approved: strategic account, BOM cost still covered (margin 11 %)."
				if flow == "approve"
				else "Rejected: 22 % would take hydraulic components below our landed cost. Offer 10 % with 60-day payment instead.",
			)
			apply_workflow(doc, "Approve" if flow == "approve" else "Reject")
		admin()
		doc.reload()
		log(f"  -> {doc.name} state {doc.workflow_state} status {doc.status}")

	# Q5 has passed its validity: run ERPNext's daily expiry job now
	from erpnext.selling.doctype.quotation.quotation import set_expired_status

	set_expired_status()


# ------------------------------------------------------------- sales orders

ORDERS = {
	# key: quote key or None, customer key, date, delivery date, po_no, address, price list, warehouse, items (when no quote)
	"SO1": ("Q1", None, "2026-08-24", "2026-09-30", "APX/PO/2026/0418", ADDRESS_MUMBAI, None, WH_FG, None),
	"SO2": ("Q2", None, "2026-09-08", "2026-09-18", "NEW/PUR/772", ADDRESS_DELHI, None, WH_DELHI_FG, None),
	"SO3": ("Q3", None, "2026-10-05", "2026-10-30", "GPW/CAP/2026/11", ADDRESS_MUMBAI, None, WH_FG, None),
	"SO4": (None, "abc", "2026-10-09", "2026-10-15", "ABC/MRO/5521", ADDRESS_MUMBAI, "HML Standard Selling", None,
		[("CMP-MOTOR-2HP", 4), ("CMP-BRG-6205", 100)]),
	"SO5": (None, "konkan", "2026-11-03", "2026-11-08", "KSS-PO-019", ADDRESS_MUMBAI, "HML Standard Selling", WH_FG,
		[("SP-BELT-600-10M", 2), ("SP-ROLLER-SET10", 3)]),
	"SO6": (None, "deccan", "2026-11-12", "2026-11-26", "DF/2026/1187", ADDRESS_MUMBAI, "HML Standard Selling", None,
		[("CMP-GEARBOX-30", 2), ("CMP-MOTOR-5HP", 2)]),
	"SO7": ("Q7", None, "2026-11-10", "2026-11-14", "ABC/MRO/5602", ADDRESS_MUMBAI, None, WH_FG, None),
}


def so_name(key):
	return frappe.db.get_value("Sales Order", {"po_no": ORDERS[key][4], "company": COMPANY, "docstatus": 1})


def step_sales_orders():
	for key, (qkey, cust_key, date, delivery, po_no, address, price_list, warehouse, items) in ORDERS.items():
		if so_name(key):
			continue
		as_user(SALES_EXEC)
		if qkey:
			doc = _make_sales_order(quote_name(qkey), ignore_permissions=True)
		else:
			doc = frappe.get_doc(
				{
					"doctype": "Sales Order",
					"customer": customer_name(cust_key),
					"company": COMPANY,
					"selling_price_list": price_list,
					"items": [{"item_code": c, "qty": q} for c, q in items],
				}
			)
		doc.update(
			{
				"transaction_date": date,
				"delivery_date": delivery,
				"po_no": po_no,
				"po_date": date,
				"company_address": address,
				"set_warehouse": warehouse,
			}
		)
		doc.payment_schedule = []  # rebuilt from the back-dated order date
		for row in doc.items:
			row.delivery_date = delivery
			if warehouse:
				row.warehouse = warehouse
		doc.insert()
		doc.submit()
		admin()
		log(f"+ Sales Order {doc.name} [{key}] {doc.customer_name} {doc.grand_total} risk={doc.hml_delivery_risk}")


# --------------------------------------------------------- packing & delivery


def _deliver(so_key, posting_date, qty_map=None, parent_warehouse=None, notes=None):
	"""SO -> Pick List -> Delivery Note (-> auto Sales Invoice)."""
	so = so_name(so_key)
	pl = create_pick_list(so)
	pl.purpose = "Delivery"
	pl.parent_warehouse = parent_warehouse
	pl.set_item_locations()
	if qty_map:
		for loc in pl.locations:
			if loc.item_code in qty_map:
				loc.qty = qty_map[loc.item_code]
				loc.stock_qty = loc.qty * flt(loc.conversion_factor or 1)
				loc.picked_qty = loc.stock_qty
	for loc in pl.locations:
		loc.picked_qty = loc.stock_qty
	pl.insert(ignore_permissions=True)
	pl.submit()
	dn = create_delivery_note(pl.name)  # ERPNext inserts the draft DN itself
	dn.reload()
	dn.set_posting_time = 1
	dn.posting_date = posting_date
	dn.posting_time = "16:00:00"
	dn.hml_deviation_notes = notes
	dn.transporter_name = None
	dn.lr_no = f"LR-{posting_date.replace('-', '')}-{so_key}"
	dn.save(ignore_permissions=True)
	dn.submit()
	si = frappe.db.get_value("Sales Invoice Item", {"delivery_note": dn.name, "docstatus": 1}, "parent")
	log(f"+ {so_key}: Pick List {pl.name} -> DN {dn.name} (deviation={dn.hml_has_deviation}) -> SI {si}")
	return dn


def step_deliveries():
	if not frappe.db.exists("Delivery Note", {"lr_no": "LR-20261013-SO4", "docstatus": 1}):
		_deliver("SO4", "2026-10-13", parent_warehouse=WH_MUMBAI)
	if not frappe.db.exists("Delivery Note", {"lr_no": "LR-20260916-SO2", "docstatus": 1}):
		_deliver(
			"SO2",
			"2026-09-16",
			qty_map={"SP-SEAL-KIT-HX": 15},
			parent_warehouse=WH_DELHI,
			notes="Partial shipment: Delhi DC held 15 seal kits. Balance 40 follows after branch transfer from Mumbai HQ.",
		)
	if not frappe.db.exists("Delivery Note", {"lr_no": "LR-20261112-SO7", "docstatus": 1}):
		_deliver("SO7", "2026-11-12", qty_map={"SP-FILTER-RET": 30}, parent_warehouse=WH_MUMBAI)


def step_branch_transfer():
	"""Mumbai HQ -> Delhi DC stock transfer between our two GSTINs.

	DN to internal customer (Mumbai FG -> Goods In Transit), priced at valuation
	rate, IGST charged because the two GSTINs are in different states; then
	Purchase Receipt from the internal supplier (Transit -> Delhi FG).
	"""
	from erpnext.stock.doctype.delivery_note.delivery_note import make_inter_company_purchase_receipt

	marker = "Branch transfer BT-2026-001"
	dn_name = frappe.db.get_value("Delivery Note", {"instructions": marker, "docstatus": 1})
	if not dn_name:
		cust = frappe.db.get_value("Customer", {"customer_name": "HML Delhi DC (Internal)"})
		dn = frappe.get_doc(
			{
				"doctype": "Delivery Note",
				"company": COMPANY,
				"customer": cust,
				"company_address": ADDRESS_MUMBAI,
				"customer_address": ADDRESS_DELHI,
				"shipping_address_name": ADDRESS_DELHI,
				"selling_price_list": "HML Standard Selling",
				"instructions": marker,
				"set_warehouse": WH_FG,
				"set_target_warehouse": WH_TRANSIT,
				"items": [{"item_code": "SP-SEAL-KIT-HX", "qty": 40, "warehouse": WH_FG, "target_warehouse": WH_TRANSIT}],
			}
		)
		dn.set_posting_time = 1
		dn.posting_date = "2026-09-21"
		dn.posting_time = "11:00:00"
		dn.insert(ignore_permissions=True)
		dn.submit()
		dn_name = dn.name
		log(f"+ Branch transfer DN {dn.name}: rate {dn.items[0].rate} taxes {dn.taxes_and_charges} total {dn.grand_total}")

	if not frappe.db.exists("Purchase Receipt Item", {"delivery_note_item": ("is", "set"), "docstatus": 1, "item_code": "SP-SEAL-KIT-HX"}):
		pr = make_inter_company_purchase_receipt(dn_name)
		pr.set_posting_time = 1
		pr.posting_date = "2026-09-24"
		pr.posting_time = "10:00:00"
		pr.billing_address = ADDRESS_DELHI
		pr.shipping_address = ADDRESS_DELHI
		pr.supplier_address = ADDRESS_MUMBAI
		pr.set_warehouse = WH_DELHI_FG
		pr.branch = BRANCH_DELHI  # mapped from the DN as HQ Mumbai; receiving side is Delhi
		for row in pr.items:
			row.branch = BRANCH_DELHI
			row.warehouse = WH_DELHI_FG
			row.from_warehouse = WH_TRANSIT
		pr.insert(ignore_permissions=True)
		pr.submit()
		log(f"+ Branch transfer PR {pr.name} into {WH_DELHI_FG}")

	# GST: an inter-GSTIN transfer is a taxable supply, so Mumbai raises a tax
	# invoice on its Delhi registration and Delhi books it for input credit.
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_inter_company_purchase_invoice
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

	if not frappe.db.exists("Sales Invoice Item", {"delivery_note": dn_name, "docstatus": 1}):
		si = make_sales_invoice(dn_name)
		si.update_stock = 0
		si.set_posting_time = 1
		si.posting_date = "2026-09-21"
		si.insert(ignore_permissions=True)
		si.submit()
		log(f"+ Branch transfer tax invoice {si.name} {si.taxes_and_charges} {si.grand_total}")
		pi = make_inter_company_purchase_invoice(si.name)
		pi.update_stock = 0
		pi.set_posting_time = 1
		pi.posting_date = "2026-09-24"
		pi.bill_no = si.name
		pi.bill_date = si.posting_date
		pi.billing_address = ADDRESS_DELHI
		pi.branch = BRANCH_DELHI
		for row in pi.items:
			row.branch = BRANCH_DELHI
		pi.supplier_address = ADDRESS_MUMBAI
		pi.insert(ignore_permissions=True)
		pi.submit()
		log(f"+ Branch transfer purchase invoice {pi.name} {pi.taxes_and_charges} {pi.grand_total}")
		for v in (si.name, pi.name):
			for g in frappe.get_all("GL Entry", filters={"voucher_no": v, "is_cancelled": 0}, fields=["account", "debit", "credit", "branch"]):
				log(f"    GL {v}: {g.account} Dr {g.debit} Cr {g.credit} [{g.branch}]")

	# balance of SO2 now ships from Delhi
	if not frappe.db.exists("Delivery Note", {"lr_no": "LR-20260926-SO2", "docstatus": 1}):
		_deliver("SO2", "2026-09-26", parent_warehouse=WH_DELHI)


STEPS = [
	("pricing_rules", step_pricing_rules),
	("leads", step_leads),
	("opportunities", step_opportunities),
	("quotations", step_quotations),
	("sales_orders", step_sales_orders),
	("deliveries", step_deliveries),
	("branch_transfer", step_branch_transfer),
]
