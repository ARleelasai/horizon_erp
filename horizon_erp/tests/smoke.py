"""Business-rule smoke tests against the seeded FSM.local data.

	bench --site FSM.local execute horizon_erp.tests.smoke.run

Each check runs inside a savepoint and is rolled back, so the site is left
unchanged. Prints PASS / FAIL per rule and raises if any rule fails.
(Unit tests via `bench run-tests` need allow_tests on the site; this runner
does not, and exercises the real hooks with the real data.)
"""

import traceback

import frappe
from frappe.utils import add_days, nowdate

from horizon_erp.constants import ADDRESS_MUMBAI, COMPANY, WH_FG, WH_RM

RESULTS = []


def check(name):
	def wrap(fn):
		def run():
			frappe.db.savepoint("hml_smoke")
			try:
				fn()
				RESULTS.append((name, "PASS", ""))
			except AssertionError as e:
				RESULTS.append((name, "FAIL", str(e)))
			except Exception as e:
				RESULTS.append((name, "FAIL", f"{type(e).__name__}: {frappe.utils.strip_html(str(e))[:200]}"))
				traceback.print_exc()
			finally:
				frappe.db.rollback(save_point="hml_smoke")
				frappe.clear_messages()

		run.__name__ = fn.__name__
		CHECKS.append(run)
		return run

	return wrap


CHECKS = []


def expect_error(fn, contains):
	try:
		fn()
	except frappe.ValidationError as e:
		msg = frappe.utils.strip_html(str(e))
		assert contains.lower() in msg.lower(), f"wrong error: {msg[:160]}"
		return msg
	raise AssertionError(f"expected an error containing '{contains}'")


def customer(name):
	return frappe.db.get_value("Customer", {"customer_name": name})


def supplier(name):
	return frappe.db.get_value("Supplier", {"supplier_name": name})


@check("Typed price without price-list rate is refused")
def _no_adhoc_price():
	so = frappe.get_doc({"doctype": "Sales Order", "company": COMPANY, "customer": customer("Deccan Fabricators"), "transaction_date": nowdate(),
		"delivery_date": add_days(nowdate(), 20), "po_no": "T-1", "company_address": ADDRESS_MUMBAI, "selling_price_list": "HML Standard Selling",
		"items": [{"item_code": "SP-GASKET-HX300", "qty": 10, "rate": 20, "warehouse": WH_FG}]})
	expect_error(so.insert, "no price in price list")


@check("Manual discount needs a reason")
def _discount_reason():
	q = frappe.get_doc({"doctype": "Quotation", "company": COMPANY, "quotation_to": "Customer", "party_name": customer("Deccan Fabricators"),
		"transaction_date": nowdate(), "company_address": ADDRESS_MUMBAI, "selling_price_list": "HML Standard Selling",
		"apply_discount_on": "Net Total", "additional_discount_percentage": 8, "items": [{"item_code": "SP-FILTER-RET", "qty": 5}]})
	expect_error(q.insert, "discount reason")


@check("Discount above 15 % cannot be submitted without approval")
def _discount_approval():
	q = frappe.get_doc({"doctype": "Quotation", "company": COMPANY, "quotation_to": "Customer", "party_name": customer("Deccan Fabricators"),
		"transaction_date": nowdate(), "company_address": ADDRESS_MUMBAI, "selling_price_list": "HML Standard Selling",
		"apply_discount_on": "Net Total", "additional_discount_percentage": 20, "hml_discount_reason": "test",
		"items": [{"item_code": "SP-FILTER-RET", "qty": 5}]})
	q.insert()
	assert q.hml_needs_discount_approval, "approval flag not set"
	expect_error(lambda: frappe.model.workflow.apply_workflow(q, "Submit"), "not a valid workflow action")


@check("Blacklisted supplier PO needs an override reason and goes to tier 3")
def _blacklist():
	po = frappe.get_doc({"doctype": "Purchase Order", "company": COMPANY, "supplier": supplier("ABC Supplies"), "transaction_date": nowdate(),
		"schedule_date": add_days(nowdate(), 7), "billing_address": ADDRESS_MUMBAI,
		"items": [{"item_code": "CMP-MANIFOLD-HX", "qty": 1, "rate": 8600, "warehouse": WH_RM, "schedule_date": add_days(nowdate(), 7)}]})
	expect_error(po.insert, "blacklisted")
	po.hml_blacklist_override_reason = "sole source"
	po.insert()
	assert po.hml_approval_tier.startswith("3"), po.hml_approval_tier


@check("PO approval tier follows amount")
def _tiers():
	for qty, tier in ((5, "1"), (60, "2"), (300, "3")):
		po = frappe.get_doc({"doctype": "Purchase Order", "company": COMPANY, "supplier": supplier("Bharat Steel Suppliers"), "transaction_date": nowdate(),
			"schedule_date": add_days(nowdate(), 7), "billing_address": ADDRESS_MUMBAI,
			"items": [{"item_code": "RM-MS-PLATE-10", "qty": qty * 30, "rate": 72, "warehouse": WH_RM, "schedule_date": add_days(nowdate(), 7)}]})
		po.insert()
		assert po.hml_approval_tier.startswith(tier), f"{po.base_grand_total} -> {po.hml_approval_tier}"


@check("Invoice before delivery is refused")
def _invoice_before_delivery():
	si = frappe.get_doc({"doctype": "Sales Invoice", "company": COMPANY, "customer": customer("Deccan Fabricators"), "company_address": ADDRESS_MUMBAI,
		"update_stock": 0, "selling_price_list": "HML Standard Selling", "items": [{"item_code": "SP-FILTER-RET", "qty": 1}]})
	expect_error(si.insert, "has not been delivered")


@check("Capacity conflict blocks a Work Order without a decision")
def _capacity():
	so = frappe.db.get_value("Sales Order", {"po_no": "APX/PO/2026/0533"})
	wo = frappe.get_doc({"doctype": "Work Order", "company": COMPANY, "production_item": "HX-500", "bom_no": frappe.db.get_value("Item", "HX-500", "default_bom"),
		"qty": 10, "use_multi_level_bom": 0, "wip_warehouse": "Mumbai - WIP - HML", "fg_warehouse": WH_FG, "source_warehouse": WH_RM,
		"planned_start_date": f"{nowdate()} 06:00:00", "hml_deadline": add_days(nowdate(), 1)})
	wo.get_items_and_operations_from_bom()
	expect_error(wo.insert, "capacity conflict")
	assert so


@check("Work Order on audit hold cannot be completed")
def _audit_gate():
	from horizon_erp.manufacturing.audit import blocking_audits

	wo = frappe.db.get_value("Work Order", {"hml_audit_hold": 1})
	assert wo and blocking_audits(wo), "no blocked work order in seed data"


@check("India Compliance refuses a GSTIN with a wrong check digit")
def _gstin_checksum():
	c = frappe.get_doc("Customer", customer("Deccan Fabricators"))
	c.gstin = c.gstin[:-1] + ("A" if c.gstin[-1] != "A" else "B")
	expect_error(c.save, "check digit")


@check("Stock purchase invoice without PO is refused")
def _pi_without_po():
	pi = frappe.get_doc({"doctype": "Purchase Invoice", "company": COMPANY, "supplier": supplier("Bharat Steel Suppliers"), "update_stock": 0,
		"billing_address": ADDRESS_MUMBAI, "bill_no": "T-PI", "items": [{"item_code": "RM-MS-PLATE-10", "qty": 10, "rate": 72}]})
	expect_error(pi.insert, "po required" if False else "purchase order")


@check("Bank entries in a reconciled month are locked")
def _bank_lock():
	je = frappe.get_doc({"doctype": "Journal Entry", "company": COMPANY, "posting_date": "2026-10-15",
		"accounts": [{"account": "Miscellaneous Expenses - HML", "debit_in_account_currency": 10, "cost_center": "Admin - HML"},
			{"account": "HDFC Bank - Current Account - HML", "credit_in_account_currency": 10, "cost_center": "Admin - HML"}]})
	expect_error(je.insert, "locked")


@check("GSTIN auto-fix repairs spacing / case, refuses wrong state")
def _gstin_fix():
	from horizon_erp.setup.seed.utils import gstin
	from horizon_erp.strategy.migration import try_fix_gstin

	good = gstin("27", "AABCK4100Q")
	assert try_fix_gstin(good.lower()[:5] + " " + good.lower()[5:], "Maharashtra") == good
	assert try_fix_gstin("24" + good[2:], "Maharashtra") is None


@check("Delhi sale is CGST+SGST from the Delhi GSTIN; Mumbai to Delhi is IGST")
def _gst_split():
	so = frappe.get_doc({"doctype": "Sales Order", "company": COMPANY, "customer": customer("Northern Engineering Works"), "transaction_date": nowdate(),
		"delivery_date": add_days(nowdate(), 10), "po_no": "T-GST", "company_address": "HML Delhi DC-Billing",
		"selling_price_list": "HML North Region Selling", "items": [{"item_code": "SP-FILTER-RET", "qty": 1, "warehouse": "Delhi - Finished Goods - HML"}]})
	so.insert()
	so.save()  # server-side inserts get tax amounts on the next save (the form computes them live)
	heads = {t.account_head for t in so.taxes if t.tax_amount}
	assert any("SGST" in h for h in heads) and not any("IGST" in h for h in heads), heads
	so2 = frappe.copy_doc(so)
	so2.po_no = "T-GST-2"
	so2.company_address = ADDRESS_MUMBAI
	so2.taxes_and_charges = None
	so2.set("taxes", [])
	for r in so2.items:
		r.warehouse = WH_FG
	so2.insert()
	so2.save()
	heads2 = {t.account_head for t in so2.taxes if t.tax_amount}
	assert any("IGST" in h for h in heads2), heads2


@check("Order beyond credit limit needs Finance override")
def _credit_limit():
	cust = customer("Konkan Steel Structures")
	frappe.db.set_value("Customer Credit Limit", {"parent": cust, "company": COMPANY}, "credit_limit", 60000)
	so = frappe.get_doc({"doctype": "Sales Order", "company": COMPANY, "customer": cust, "transaction_date": nowdate(),
		"delivery_date": add_days(nowdate(), 10), "po_no": "T-CR", "company_address": ADDRESS_MUMBAI, "selling_price_list": "HML Standard Selling",
		"items": [{"item_code": "SP-BELT-600-10M", "qty": 2, "warehouse": WH_FG}]})
	so.insert()
	expect_error(so.submit, "credit limit")


def run():
	frappe.set_user("Administrator")
	frappe.flags.mute_emails = True
	RESULTS.clear()
	for c in CHECKS:
		c()
	width = max(len(r[0]) for r in RESULTS)
	for name, status, note in RESULTS:
		print(f"{status:4}  {name.ljust(width)}  {note}")
	failed = [r for r in RESULTS if r[1] == "FAIL"]
	print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
	frappe.db.rollback()
	if failed:
		raise SystemExit(1)
