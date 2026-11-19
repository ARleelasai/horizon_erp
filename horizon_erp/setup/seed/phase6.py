"""Phase 6 - Accounts, GST, development tasks and strategic challenges.

Bank account and opening balance, supplier invoices and customer receipts,
payment batches through both approval levels, bank statement lines with
auto-match, exceptions and the October reconciliation lock; budgets (cost
center and location) with a Q4-weighted distribution and an approved
overage; reverse-charge purchase; ABC Corp net settlement; the
quality-vs-deadline scenario (weld defect two days before a Friday
delivery); legacy data staging rows; an obsolete item scrapped; the Delhi DC
API client; and one run of every scheduled job.
"""

import json
import zlib

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, flt, getdate

from horizon_erp.constants import (
	ADDRESS_MUMBAI,
	BRANCH_DELHI,
	BRANCH_MUMBAI,
	COMPANY,
	WH_FG,
	WH_MUMBAI,
	acc,
	cc,
)
from horizon_erp.setup.seed.phase1 import customer_name, supplier_name, user_email
from horizon_erp.setup.seed.utils import ensure_value, get_or_insert, gstin, log

HDFC = "HDFC Current - HDFC Bank"  # Bank Account name: <account_name> - <bank>
HDFC_GL = "HDFC Bank - Current Account - HML"
FD = user_email("rajesh.menon")
ACCOUNTS_USER = user_email("sunita.pawar")
BUYER = user_email("pooja.shah")


def admin():
	frappe.set_user("Administrator")


def as_user(u):
	frappe.set_user(u)


# ------------------------------------------------------------- bank masters


def step_bank_masters():
	get_or_insert("Bank", "HDFC Bank", {"bank_name": "HDFC Bank", "swift_number": "HDFCINBB"})
	if not frappe.db.exists("Bank Account", HDFC):
		frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": "HDFC Current",
				"bank": "HDFC Bank",
				"account": acc("HDFC Bank - Current Account"),
				"company": COMPANY,
				"is_company_account": 1,
				"is_default": 1,
				"bank_account_no": "50200012345678",
				"branch_code": "HDFC0000212",
				"hml_reconciliation_frequency": "Monthly",
			}
		).insert(ignore_permissions=True)
	# beneficiary bank details for the transfer file
	for key, no, ifsc in (("bharat", "002105001122", "ICIC0000021"), ("shree", "31210100045219", "BARB0VASAIX"),
			("delhielec", "915020045553311", "UTIB0000049"), ("hydrotech", "1234500098761", "KKBK0008067")):
		sup = supplier_name(key)
		name = f"{frappe.db.get_value('Supplier', sup, 'supplier_name')} - {no[-4:]}"
		if not frappe.db.exists("Bank Account", {"party": sup}):
			frappe.get_doc(
				{"doctype": "Bank Account", "account_name": name, "bank": "HDFC Bank", "party_type": "Supplier", "party": sup,
					"bank_account_no": no, "branch_code": ifsc}
			).insert(ignore_permissions=True)

	# opening bank balance at go-live (1 Apr 2026)
	if not frappe.db.exists("Journal Entry", {"company": COMPANY, "user_remark": "Opening balance HDFC current account at go-live"}):
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": COMPANY,
				"voucher_type": "Opening Entry",
				"is_opening": "Yes",
				"posting_date": "2026-04-01",
				"user_remark": "Opening balance HDFC current account at go-live",
				"accounts": [
					{"account": acc("HDFC Bank - Current Account"), "debit_in_account_currency": 25000000, "cost_center": cc("Admin")},
					{"account": acc("Temporary Opening"), "credit_in_account_currency": 25000000, "cost_center": cc("Admin")},
				],
			}
		)
		je.insert(ignore_permissions=True)
		je.submit()
		log(f"+ Opening bank balance {je.name}")

	# owners, terms, payment terms
	for center, user in (("Mfg - Equipment", "priya.nair"), ("Mfg - Spares", "priya.nair"), ("Mfg - Components", "priya.nair"),
			("Sales", "amit.kapoor"), ("Admin", "rajesh.menon"), ("R&D", "priya.nair")):
		frappe.db.set_value("Cost Center", cc(center), "hml_owner", user_email(user))
	frappe.db.set_value(
		"Company", COMPANY, "hml_invoice_terms",
		"<ol><li>Payment due as per the due date shown; 18 % p.a. interest on overdue amounts.</li>"
		"<li>Goods once dispatched are at the buyer's risk; claims for transit damage within 7 days of receipt.</li>"
		"<li>Warranty: 12 months from dispatch against manufacturing defects (excludes wear parts and seals).</li>"
		"<li>Subject to Mumbai jurisdiction.</li></ol>",
	)
	frappe.db.set_value("Company", COMPANY, "exception_budget_approver_role", "HML Finance Director")
	get_or_insert(
		"Payment Terms Template", "HML Net 30",
		{"template_name": "HML Net 30", "terms": [{"invoice_portion": 100, "credit_days": 30, "due_date_based_on": "Day(s) after invoice date",
			"description": "Net 30"}]},
		set_name="HML Net 30",
	)
	for key in ("apex", "northern", "deccan", "sahyadri", "capital", "abc", "gujarat"):
		frappe.db.set_value("Customer", customer_name(key), "payment_terms", "HML Net 30")


# ------------------------------------------------- supplier invoices, receipts


def _bill_receipts():
	"""Purchase invoices for every GRN not yet billed (supplier bill 2 days later)."""
	billed = []
	for pr in frappe.get_all(
		"Purchase Receipt",
		filters={"company": COMPANY, "docstatus": 1, "is_return": 0, "per_billed": ("<", 100), "is_internal_supplier": 0},
		fields=["name", "posting_date", "supplier"],
		order_by="posting_date",
	):
		pi = make_purchase_invoice(pr.name)
		pi.posting_date = add_days(pr.posting_date, 2)
		pi.set_posting_time = 1
		pi.bill_no = f"S-{zlib.crc32(pr.name.encode()) % 100000:05d}"
		pi.bill_date = pi.posting_date
		pi.update_stock = 0
		pi.due_date = None
		pi.payment_schedule = []
		pi.insert(ignore_permissions=True)
		pi.submit()
		billed.append((pi.name, pr.name, pi.grand_total))
	return billed


def step_purchase_invoices():
	# ABC Corp also supplies us (customer-supplier overlap)
	from horizon_erp.setup.seed import phase3

	if not phase3.po_name("PO11"):
		phase3.POS = {"PO11": ("abc", "2026-10-28", "2026-11-04", [("CMP-GEARBOX-30", 10, 9800)], "Normal", "approve", {})}
		phase3.RECEIPTS = [("PO11", "2026-11-04", "11:00:00", [("CMP-GEARBOX-30", "Pass", 0, None, None)], 1.5)]
		phase3.step_purchase_orders()
		phase3.step_receipts()
	for name, pr, total in _bill_receipts():
		log(f"+ Purchase Invoice {name} for {pr}: Rs {total:,.0f}")


def step_rcm_purchase():
	"""Job-work service from an unregistered supplier -> reverse charge (HML rule)."""
	if frappe.db.exists("Purchase Invoice", {"bill_no": "SF/JW/2026/118"}):
		return
	from horizon_erp.setup.seed.phase1 import _ensure_hsn

	if not frappe.db.exists("Item", "SRV-MACHINING"):
		_ensure_hsn("998898")
		frappe.get_doc(
			{"doctype": "Item", "item_code": "SRV-MACHINING", "item_name": "Job work - machining of flanges", "item_group": "Services",
				"stock_uom": "Nos", "is_stock_item": 0, "is_purchase_item": 1, "is_sales_item": 0, "has_batch_no": 0, "has_expiry_date": 0,
				"gst_hsn_code": "998898",
				"item_defaults": [{"company": COMPANY, "default_warehouse": WH_FG, "expense_account": acc("Contract Labour Charges"),
					"buying_cost_center": cc("Mfg - Equipment")}]}
		).insert(set_name="SRV-MACHINING", ignore_permissions=True)
	pi = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"company": COMPANY,
			"supplier": supplier_name("shree"),
			"posting_date": "2026-11-07",
			"set_posting_time": 1,
			"bill_no": "SF/JW/2026/118",
			"bill_date": "2026-11-07",
			"update_stock": 0,
			"billing_address": ADDRESS_MUMBAI,
			"items": [{"item_code": "SRV-MACHINING", "qty": 40, "rate": 650, "item_tax_template": "GST 18% - HML"}],
		}
	)
	pi.insert(ignore_permissions=True)
	pi.submit()
	log(f"+ RCM purchase {pi.name}: reverse charge {pi.is_reverse_charge}, taxes {[(t.account_head, t.tax_amount) for t in pi.taxes]}")


def step_customer_receipts():
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	skip = {customer_name("abc"), customer_name("apex")}  # ABC is netted; Apex pays after delivery acceptance
	for si in frappe.get_all(
		"Sales Invoice",
		filters={"company": COMPANY, "docstatus": 1, "is_return": 0, "outstanding_amount": (">", 0), "is_internal_customer": 0},
		fields=["name", "customer", "posting_date", "outstanding_amount"],
		order_by="posting_date",
	):
		if si.customer in skip or frappe.db.get_value("Customer", si.customer, "customer_name") == "Om Scrap Traders":
			continue
		pay_date = add_days(si.posting_date, 20)
		if getdate(pay_date) > getdate("2026-11-17"):
			continue
		pe = get_payment_entry("Sales Invoice", si.name, bank_account=HDFC_GL)
		pe.posting_date = pay_date
		pe.mode_of_payment = "Wire Transfer"
		pe.reference_no = f"UTR{zlib.crc32(si.name.encode()) % 10**10:010d}"
		pe.reference_date = pay_date
		pe.insert(ignore_permissions=True)
		pe.submit()
		log(f"+ Receipt {pe.name} {si.customer} Rs {pe.paid_amount:,.0f} on {pay_date}")
	# the scrap buyer paid by cheque - deposited, still in clearing on 18 Nov
	si = frappe.db.get_value("Sales Invoice", {"customer": frappe.db.get_value("Customer", {"customer_name": "Om Scrap Traders"}), "docstatus": 1, "outstanding_amount": (">", 0)})
	if si:
		pe = get_payment_entry("Sales Invoice", si, bank_account=HDFC_GL)
		pe.posting_date = "2026-11-17"
		pe.mode_of_payment = "Cheque"
		pe.reference_no = "CHQ 004417"
		pe.reference_date = "2026-11-17"
		pe.insert(ignore_permissions=True)
		pe.submit()
		log(f"+ Cheque receipt {pe.name} (in clearing)")


def step_supplier_payments():
	"""Old July bills paid directly; Oct/Nov bills through payment batches."""
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	for pi in frappe.get_all("Purchase Invoice", filters={"company": COMPANY, "docstatus": 1, "outstanding_amount": (">", 0),
			"posting_date": ("<", "2026-08-01"), "is_return": 0}, fields=["name", "posting_date"]):
		pe = get_payment_entry("Purchase Invoice", pi.name, bank_account=HDFC_GL)
		pe.posting_date = add_days(pi.posting_date, 30)
		pe.mode_of_payment = "Wire Transfer"
		pe.reference_no = f"NEFT{zlib.crc32(pi.name.encode()) % 10**8:08d}"
		pe.reference_date = pe.posting_date
		pe.insert(ignore_permissions=True)
		pe.submit()
		log(f"+ Supplier payment {pe.name} for {pi.name}")

	def batch(title, invoices, date):
		if frappe.db.exists("Payment Batch", {"title": ("like", f"%{title}%")}) or frappe.db.exists("Payment Batch Item", {"purchase_invoice": invoices[0]}):
			return None
		as_user(ACCOUNTS_USER)
		pb = frappe.get_doc(
			{
				"doctype": "Payment Batch",
				"company": COMPANY,
				"bank_account": HDFC,
				"posting_date": date,
				"items": [
					{"purchase_invoice": inv, "amount": frappe.db.get_value("Purchase Invoice", inv, "outstanding_amount"),
						"supplier": frappe.db.get_value("Purchase Invoice", inv, "supplier"),
						"mode": "Cheque" if frappe.db.get_value("Purchase Invoice", inv, "supplier") == supplier_name("shree") else "NEFT",
						"cheque_no": "000781" if frappe.db.get_value("Purchase Invoice", inv, "supplier") == supplier_name("shree") else None}
					for inv in invoices
				],
			}
		)
		pb.insert()
		apply_workflow(pb, "Submit for Approval")
		pb.reload()
		as_user(FD)
		apply_workflow(pb, "Approve")
		admin()
		pb.reload()
		log(f"+ Payment Batch {pb.name} ({pb.approval_level}): {pb.title}; file {pb.transfer_file}; cheques {pb.cheque_count}")
		return pb

	def bill_for(po_key):
		from horizon_erp.setup.seed import phase3

		po = phase3.po_name(po_key)
		return frappe.db.get_value("Purchase Invoice Item", {"purchase_order": po, "docstatus": 1}, "parent")

	batch("Batch Nov-1", [b for b in (bill_for("PO1"), bill_for("PO2")) if b], "2026-11-10")
	batch("Batch Nov-2", [b for b in (bill_for("PO4"),) if b], "2026-11-16")


# --------------------------------------------------------- bank statement


def step_bank_statement():
	if frappe.db.exists("Bank Transaction", {"bank_account": HDFC}):
		return
	account = acc("HDFC Bank - Current Account")
	opening = flt(frappe.db.sql(
		"select sum(debit - credit) from `tabGL Entry` where account = %s and is_cancelled = 0 and posting_date < '2026-10-01'", account)[0][0])
	frappe.db.set_value("Bank Account", HDFC, "hml_statement_opening", opening)
	lines = []
	for v in frappe.db.sql(
		"""select 'PE' t, name, posting_date d, reference_no ref, if(paid_to = %(a)s, paid_amount, -paid_amount) amt, mode_of_payment mode
		from `tabPayment Entry` where docstatus = 1 and (paid_to = %(a)s or paid_from = %(a)s) and posting_date >= '2026-10-01'
		union all
		select 'JE', je.name, je.posting_date, je.cheque_no, jea.debit - jea.credit, null
		from `tabJournal Entry` je join `tabJournal Entry Account` jea on jea.parent = je.name
		where je.docstatus = 1 and jea.account = %(a)s and je.posting_date >= '2026-10-01'""",
		{"a": account}, as_dict=True,
	):
		if v.mode == "Cheque" and flt(v.amt) > 0:
			continue  # deposited cheque still in clearing - not on the statement yet
		bank_date = v.d if not (v.mode == "Cheque" and flt(v.amt) < 0) else add_days(v.d, 3)  # issued cheque presented later
		lines.append((getdate(bank_date), flt(v.amt), v.ref or v.name, f"{v.t} {v.name}"))
	lines += [
		(getdate("2026-10-31"), -590.0, "CHG-OCT", "SMS / NEFT charges Oct"),
		(getdate("2026-10-31"), 1245.0, "INT-OCT", "Sweep interest Oct"),
		(getdate("2026-11-12"), 25000.0, "NEFT-UNKNOWN-9921", "NEFT CR - REF 9921 - KONKAN STL"),
	]
	for d, amt, ref, desc in sorted(lines):
		bt = frappe.get_doc(
			{
				"doctype": "Bank Transaction",
				"date": d,
				"bank_account": HDFC,
				"company": COMPANY,
				"deposit": amt if amt > 0 else 0,
				"withdrawal": -amt if amt < 0 else 0,
				"currency": "INR",
				"reference_number": ref,
				"description": desc,
			}
		)
		bt.insert(ignore_permissions=True)
		bt.submit()
	log(f"+ {len(lines)} bank statement lines imported (opening Rs {opening:,.0f})")


def step_reconcile():
	from horizon_erp.accounts.bank import auto_match

	res = auto_match(HDFC, "2026-11-18")
	log(f"+ auto-match: {len(res['matched'])} matched, {len(res['left_for_manual'])} left for manual review")
	for ref, typ, note in (("CHG-OCT", "Bank Charge to Book", "Book via JE in November (bank charges)"),
			("INT-OCT", "Interest to Book", "Book via JE in November (interest income)"),
			("NEFT-UNKNOWN-9921", "Unidentified Receipt", "Likely Konkan Steel advance - confirm with customer")):
		bt = frappe.db.get_value("Bank Transaction", {"bank_account": HDFC, "reference_number": ref})
		frappe.db.set_value("Bank Transaction", bt, {"hml_exception_type": typ, "hml_exception_note": note})
	if not frappe.db.exists("Bank Reconciliation Lock", {"bank_account": HDFC, "period_end": "2026-10-31"}):
		account = acc("HDFC Bank - Current Account")
		stmt = flt(frappe.db.get_value("Bank Account", HDFC, "hml_statement_opening")) + flt(frappe.db.sql(
			"select sum(deposit - withdrawal) from `tabBank Transaction` where bank_account = %s and docstatus = 1 and date <= '2026-10-31'", HDFC)[0][0])
		as_user(FD)
		lock = frappe.get_doc({"doctype": "Bank Reconciliation Lock", "bank_account": HDFC, "period_end": "2026-10-31", "statement_balance": stmt,
			"notes": "October reconciled. Bank charges and sweep interest to be booked in November."})
		lock.insert()
		lock.submit()
		admin()
		log(f"+ {lock.name}: statement {stmt:,.0f}, GL {lock.gl_balance:,.0f}, explained {lock.explained_difference:,.0f}, unexplained {lock.unexplained:,.0f}")
	# the lock bites: an October-dated bank entry is refused
	je = frappe.get_doc({"doctype": "Journal Entry", "company": COMPANY, "posting_date": "2026-10-30",
		"accounts": [{"account": acc("Miscellaneous Expenses"), "debit_in_account_currency": 100, "cost_center": cc("Admin")},
			{"account": acc("HDFC Bank - Current Account"), "credit_in_account_currency": 100, "cost_center": cc("Admin")}]})
	try:
		je.insert(ignore_permissions=True)
		log("  !! lock did not block")
	except frappe.ValidationError as e:
		frappe.clear_last_message()
		log(f"  lock check: {frappe.utils.strip_html(str(e))[:100]}")


# ----------------------------------------------------------------- budgets

BUDGETS = [
	# cost center, [(account, annual)]
	("Mfg - Equipment", [("Repairs and Maintenance - Plant", 200000), ("Factory Power and Fuel", 2600000), ("Factory Rent", 4200000)]),
	("Admin", [("Utility Expenses", 600000), ("Scrap and Obsolescence Loss", 50000), ("Miscellaneous Expenses", 100000)]),
	("Sales", [("Warehouse Rent", 1440000)]),
	("R&D", [("R&D Expenses", 500000)]),
]
BRANCH_BUDGETS = [
	(BRANCH_MUMBAI, [("Factory Rent", 4200000), ("Factory Power and Fuel", 2600000), ("Utility Expenses", 600000), ("Repairs and Maintenance - Plant", 200000)]),
	(BRANCH_DELHI, [("Warehouse Rent", 1440000)]),
]


def step_budgets():
	if not frappe.db.exists("Monthly Distribution", "HML Q4 Weighted"):
		md = frappe.get_doc({"doctype": "Monthly Distribution", "distribution_id": "HML Q4 Weighted", "fiscal_year": "2026-2027"})
		md.get_months()
		for row in md.percentages:
			row.percentage_allocation = 10.8333 if row.month in ("January", "February", "March") else 7.5
		md.percentages[-1].percentage_allocation += 100 - sum(flt(r.percentage_allocation) for r in md.percentages)
		md.insert(ignore_permissions=True)
	for center, rows in BUDGETS:
		if frappe.db.exists("Budget", {"cost_center": cc(center), "fiscal_year": "2026-2027", "docstatus": 1}):
			continue
		b = frappe.get_doc(
			{
				"doctype": "Budget", "budget_against": "Cost Center", "cost_center": cc(center), "company": COMPANY, "fiscal_year": "2026-2027",
				"monthly_distribution": "HML Q4 Weighted", "applicable_on_booking_actual_expenses": 1,
				"action_if_annual_budget_exceeded": "Stop", "action_if_accumulated_monthly_budget_exceeded": "Warn",
				"accounts": [{"account": acc(a), "budget_amount": amt} for a, amt in rows],
			}
		)
		b.insert(ignore_permissions=True)
		b.submit()
		log(f"+ Budget {b.name}")
	for branch, rows in BRANCH_BUDGETS:
		if frappe.db.exists("Budget", {"branch": branch, "fiscal_year": "2026-2027", "docstatus": 1}):
			continue
		b = frappe.get_doc(
			{
				"doctype": "Budget", "budget_against": "Branch", "branch": branch, "company": COMPANY, "fiscal_year": "2026-2027",
				"monthly_distribution": "HML Q4 Weighted", "applicable_on_booking_actual_expenses": 1,
				"action_if_annual_budget_exceeded": "Warn", "action_if_accumulated_monthly_budget_exceeded": "Ignore",
				"accounts": [{"account": acc(a), "budget_amount": amt} for a, amt in rows],
			}
		)
		b.insert(ignore_permissions=True)
		b.submit()
		log(f"+ Location budget {b.name}")


def step_budget_overage():
	"""Emergency repair pushes Repairs & Maintenance past its annual budget."""
	if frappe.db.exists("Budget Overage Approval", {"docstatus": 1}):
		return
	as_user(ACCOUNTS_USER)
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"company": COMPANY,
			"posting_date": "2026-11-16",
			"title": "Emergency repair - Line A hydraulic press",
			"user_remark": "Emergency repair of Line A 200 T press main cylinder (breakdown 14 Nov)",
			"cheque_no": "NEFT-NOV-REPAIR-01",
			"cheque_date": "2026-11-16",
			"accounts": [
				{"account": acc("Repairs and Maintenance - Plant"), "debit_in_account_currency": 65000, "cost_center": cc("Mfg - Equipment")},
				{"account": acc("HDFC Bank - Current Account"), "credit_in_account_currency": 65000, "cost_center": cc("Mfg - Equipment")},
			],
		}
	)
	je.insert()
	frappe.db.savepoint("hml_before_budget_submit")
	try:
		je.submit()
		log("  !! budget did not stop the entry")
		admin()
		return
	except frappe.ValidationError as e:
		frappe.db.rollback(save_point="hml_before_budget_submit")
		frappe.clear_last_message()
		log(f"  budget stopped JE {je.name}: {frappe.utils.strip_html(str(e))[:110]}...")
	je.reload()
	boa = frappe.get_doc(
		{
			"doctype": "Budget Overage Approval",
			"reference_doctype": "Journal Entry",
			"reference_name": je.name,
			"company": COMPANY,
			"cost_center": cc("Mfg - Equipment"),
			"account": acc("Repairs and Maintenance - Plant"),
			"reason": "Line A stopped since 14 Nov; HX-500 orders (Apex, Gujarat) blocked. Repair is cheaper than 3 more days of downtime (Rs 1.4 L/day).",
		}
	)
	boa.insert()
	admin()
	as_user(FD)
	boa.reload()
	boa.add_comment("Comment", "Approved - add Rs 1.5 L to the R&M budget in the Q4 re-forecast.")
	apply_workflow(boa, "Approve")
	admin()
	log(f"+ {boa.name}: overage Rs {frappe.db.get_value('Budget Overage Approval', boa.name, 'overage'):,.0f} approved; JE {je.name} status {frappe.db.get_value('Journal Entry', je.name, 'docstatus')}")


# -------------------------------------------------------- strategic: ABC Corp


def step_net_settlement():
	from horizon_erp.strategy.parties import create_contra_entry, linked_parties

	if frappe.db.exists("Journal Entry", {"company": COMPANY, "voucher_type": "Contra Entry", "docstatus": 1}):
		return
	pos = next(p for p in linked_parties() if frappe.db.get_value("Customer", p.customer, "customer_name") == "ABC Corp")
	amount = min(pos.receivable, pos.payable, 100000)
	name = create_contra_entry(pos.customer, pos.supplier, amount, "2026-11-18",
		"Net settlement agreed with ABC Corp (letter ABC/FIN/1118): our payable for gearboxes set off against their components invoices")
	je = frappe.get_doc("Journal Entry", name)
	je.submit()
	log(f"+ ABC Corp: receivable {pos.receivable:,.0f}, payable {pos.payable:,.0f}; contra {name} for {amount:,.0f}")


# -------------------------------------------- strategic: quality vs deadline


def step_quality_deadline():
	"""Wednesday 18 Nov: 3 conveyors for Capital Machinery ship Friday 20 Nov.
	Final test finds a weld crack on 1 of 3 frames (33 %); rework line is full."""
	from horizon_erp.setup.seed.phase4 import (
		LINE_B,
		_complete_job_card,
		_inspect_job_card,
		_stock_entry,
		_wo,
		run_work_order,
	)

	so = frappe.db.get_value("Sales Order", {"po_no": "CMT/2026/311"})
	if not so or frappe.db.exists("Quality Deadline Decision", {"sales_order": so}):
		return
	frappe.db.set_value("Sales Order", so, "delivery_date", "2026-11-20")
	frappe.db.sql("update `tabSales Order Item` set delivery_date = '2026-11-20' where parent = %s", so)
	run_work_order(_wo("SA-CX-FRAME", 3, "2026-11-16", LINE_B, description="CX-200 lot 2 frames"), "2026-11-16")
	run_work_order(_wo("SA-CX-DRIVE", 3, "2026-11-16", LINE_B, description="CX-200 lot 2 drives"), "2026-11-16")
	wo = frappe.get_doc("Work Order", frappe.db.get_value("Work Order", {"sales_order": so, "production_item": "CX-200"}))
	wo.hml_deadline = "2026-11-18"
	wo.hml_capacity_decision = wo.hml_capacity_decision or "Overtime / Extra Shift"
	wo.hml_capacity_decision_note = wo.hml_capacity_decision_note or "Distributor order pulled in to 20 Nov; afternoon shift overtime on 17-18 Nov."
	wo.save(ignore_permissions=True)
	wo.submit()
	_stock_entry(wo, "Material Transfer for Manufacture", 3, "2026-11-17 06:30:00")
	asm = frappe.db.get_value("Job Card", {"work_order": wo.name, "operation": "HML Assembly"})
	jc = _complete_job_card(asm, "2026-11-17 07:00:00", 360)
	_inspect_job_card(jc, "Pass", "2026-11-17 13:30:00")
	jc.reload()
	jc.submit()
	test = frappe.db.get_value("Job Card", {"work_order": wo.name, "operation": "HML Testing"})
	tjc = _complete_job_card(test, "2026-11-18 07:00:00", 90)
	_inspect_job_card(tjc, "Rework", "2026-11-18 08:45:00", rejected_qty=1, reason="Weld defect - porosity / undercut",
		remarks="Load test: crack at conveyor frame cross-member weld on unit 3. Units 1-2 passed.")
	qi = frappe.get_doc({"doctype": "Quality Inspection", "inspection_type": "In Process", "reference_type": "Job Card", "reference_name": tjc.name,
		"item_code": "CX-200", "sample_size": 2, "report_date": "2026-11-18", "inspected_by": user_email("ramesh.iyer"),
		"quality_inspection_template": "HML Op - Final Test", "hml_result": "Pass", "manual_inspection": 1,
		"hml_evidence_photo": "/assets/frappe/images/default-avatar.png", "remarks": "Units 1 and 2 passed load and noise test."})
	qi.get_item_specification_details()
	for r in qi.readings:
		r.status = "Accepted"
		r.reading_value = r.value
		if r.numeric:
			r.reading_1 = str((r.min_value + r.max_value) / 2)
	qi.insert(ignore_permissions=True)
	qi.submit()
	tjc.reload()
	tjc.submit()
	_stock_entry(wo, "Manufacture", 2, "2026-11-18 11:00:00")
	log(f"+ {wo.name}: 2 of 3 CX-200 passed; 1 in rework (rework job card open)")

	from horizon_erp.strategy.conflicts import scan_conflicts

	raised = scan_conflicts(today="2026-11-18")["raised"]
	name = frappe.db.get_value("Quality Deadline Decision", {"sales_order": so})
	qdd = frappe.get_doc("Quality Deadline Decision", name)
	qdd.update(
		{
			"sales_position": "Capital Machinery has a site handover on 23 Nov; 2 units on Friday cover their first bay.",
			"operations_position": qdd.operations_position + "; rework queue on Line A/B full until 24 Nov (HX-500 orders).",
			"quality_position": "Unit 3 cannot ship: weld crack is a safety defect. Units 1-2 passed load test.",
			"finance_position": "Wanted all 3 invoiced Friday for the quarter target; accepts invoicing the 2 shipped units only - customer has not asked for bill-and-hold.",
			"rework_hours_needed": 3,
			"rework_hours_free": 0,
			"cost_of_delay_per_day": 2500,
			"delay_days": 7,
			"cost_of_quality": 4800,
			"expedite_cost": 0,
			"decision": "Ship Partial + Rework Balance",
			"decision_rationale": "Ship the 2 passed units Friday, rework unit 3 on 24 Nov, deliver 27 Nov. Shipping the cracked unit is not an option; waiting for all 3 costs the customer their site date.",
			"ship_now_qty": 2,
			"new_delivery_date": "2026-11-27",
			"customer_agreed": 1,
		}
	)
	qdd.save(ignore_permissions=True)
	for user in ("amit.kapoor", "priya.nair", "ramesh.iyer", "rajesh.menon"):
		as_user(user_email(user))
		frappe.get_doc("Quality Deadline Decision", name).acknowledge()
	as_user(user_email("priya.nair"))
	qdd = frappe.get_doc("Quality Deadline Decision", name)
	qdd.lessons = "Add weld dye-penetrant check after frame welding (before assembly) so cracks are found 2 days earlier."
	qdd.submit()
	admin()
	log(f"+ {name} raised by the scan ({raised}) and decided: {qdd.decision}")


# ------------------------------------------------------ data migration rows


def step_migration_staging():
	if frappe.db.count("Migration Staging Row"):
		return
	rows = []
	states = ["Maharashtra", "Gujarat", "Karnataka", "Delhi"]
	for i in range(50):
		state = states[i % 4]
		pan = f"AAB{'CFHPT'[i % 5]}{'KLMNP'[i % 5]}{4100 + i}{'QRSTU'[i % 5]}"
		good = gstin({"Maharashtra": "27", "Gujarat": "24", "Karnataka": "29", "Delhi": "07"}[state], pan)
		if i < 15:
			bad, issue = good.lower()[:7] + " " + good.lower()[7:], "Invalid GSTIN"  # spacing / case
		elif i < 25:
			bad, issue = good[:7] + good[7:11].replace("1", "I").replace("0", "O") + good[11:], "Invalid GSTIN"  # OCR swap
			if bad == good:
				bad = good[:8] + "O" + good[9:] if good[8] == "0" else good[:-1] + ("A" if good[-1] != "A" else "B")
		elif i < 35:
			wrong = {"Maharashtra": "24", "Gujarat": "27", "Karnataka": "33", "Delhi": "09"}[state]
			bad, issue = wrong + good[2:], "GSTIN State Mismatch"
		elif i < 45:
			bad, issue = good[:-1] + ("Z" if good[-1] != "Z" else "Y"), "Invalid GSTIN"
		else:
			bad, issue = good[:11], "Invalid GSTIN"
		rows.append({"entity": "Customer", "legacy_id": f"LC{1000 + i}", "legacy_name": f"Legacy Customer {i + 1:02d}", "issue": issue,
			"original_value": bad, "payload": json.dumps({"state": state, "pan": pan})})
	items = ["CMP-BRG-6205", "RM-BOLT-M12", "RM-WELD-E7018", "SP-FILTER-RET", "CMP-ROLLER-50", "RM-PAINT-EPOXY", "SP-HOSE-KIT"]
	for i in range(100):
		item = items[i % len(items)]
		rate = flt(frappe.db.get_value("Item", item, "valuation_rate")) or 100
		qty = -(1 + (i * 7) % 15) if i < 70 else -(40 + i)
		serial = 1 if 90 <= i < 100 else 0
		if i >= 70 and i < 90:
			rate = rate * 6
		rows.append({"entity": "Item Stock", "legacy_id": f"LS{2000 + i}", "legacy_name": f"{item} @ legacy bin {i % 9 + 1}", "issue": "Negative Stock",
			"qty": qty, "payload": json.dumps({"item_code": item, "valuation_rate": rate, "serial_or_batch": serial})})
	for i in range(25):
		stock = 12 <= i < 20
		amount = 18000 + i * 1500 if i < 20 else 64000 + i * 2000
		rows.append({"entity": "Purchase Invoice", "legacy_id": f"LPI{3000 + i}", "legacy_name": ["Electricity bill", "Courier", "AMC - compressor", "Raw material"][i % 4],
			"issue": "Purchase Invoice Without PO", "amount": amount, "payload": json.dumps({"has_stock_items": stock})})
	for r in rows:
		frappe.get_doc({"doctype": "Migration Staging Row", "status": "Pending", **r}).insert(ignore_permissions=True)
	from horizon_erp.strategy.migration import classify_staging_rows

	result = classify_staging_rows()
	log(f"+ Migration staging: {len(rows)} legacy rows -> {result}")


# ----------------------------------------------------------- obsolete stock


def step_obsolete_stock():
	if frappe.db.exists("Item", "SP-GASKET-HX300"):
		return
	from horizon_erp.setup.seed.phase1 import _ensure_hsn

	_ensure_hsn("40169320")
	frappe.get_doc(
		{"doctype": "Item", "item_code": "SP-GASKET-HX300", "item_name": "HX-300 Cylinder Gasket (discontinued model)", "item_group": "Spares",
			"stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 1, "is_purchase_item": 0, "has_batch_no": 0, "has_expiry_date": 0,
			"valuation_rate": 85, "gst_hsn_code": "40169320", "item_defaults": [{"company": COMPANY, "default_warehouse": WH_FG}]}
	).insert(set_name="SP-GASKET-HX300", ignore_permissions=True)
	se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": COMPANY, "set_posting_time": 1,
		"posting_date": "2026-04-01", "posting_time": "08:30:00", "remarks": "Legacy stock of discontinued HX-300 gaskets brought in at go-live",
		"items": [{"item_code": "SP-GASKET-HX300", "qty": 120, "basic_rate": 85, "t_warehouse": WH_FG, "expense_account": acc("Temporary Opening"),
			"cost_center": cc("Admin")}]})
	se.insert(ignore_permissions=True)
	se.submit()
	from horizon_erp.horizon_erp.report.inventory_obsolescence_analysis.inventory_obsolescence_analysis import create_scrap_note, execute

	_cols, data, *_ = execute({"days_threshold": 90, "only_above_threshold": 1})
	rows = [r for r in data if r["item_code"] == "SP-GASKET-HX300"]
	as_user(user_email("priya.nair"))
	note = frappe.get_doc("Scrap Note", create_scrap_note(rows, "HX-300 model discontinued in 2023; no sale since go-live; gaskets hardened (age) - not saleable."))
	note.posting_date = "2026-11-18"
	note.save()
	note.submit()
	admin()
	log(f"+ Scrap Note {note.name}: Rs {note.total_value:,.0f} written off via {note.stock_entry}")


# --------------------------------------------------------------- API client


def step_api_client():
	user = user_email("delhi.dc.api")
	if not frappe.db.get_value("User", user, "api_key"):
		from frappe.core.doctype.user.user import generate_keys

		generate_keys(user)
	get_or_insert("API Client", "Delhi DC Sync", {"client_name": "Delhi DC Sync", "user": user, "enabled": 1, "rate_limit_per_hour": 100,
		"allowed_warehouses": "Delhi DC\nDelhi - Finished Goods"})
	from horizon_erp.api.inventory import get_inventory_snapshot

	as_user(user)
	ok = get_inventory_snapshot("Delhi DC", True)
	bad = get_inventory_snapshot("Pune DC", False)
	admin()
	frappe.local.response.pop("http_status_code", None)
	log(f"+ API Client Delhi DC Sync: snapshot {len(ok.get('items', []))} items / {len(ok.get('low_stock_alerts', []))} alerts; invalid warehouse -> {bad.get('status')}")


# ------------------------------------------------------------ job runs


def step_run_jobs():
	from horizon_erp.tasks.jobs import retry_failed_jobs, run_logged

	if frappe.db.count("Integration Log"):
		return
	for job, method in (("Hourly inventory: reorder + accuracy", "horizon_erp.tasks.jobs.hourly_inventory_job"),
			("Daily Finance Director summary", "horizon_erp.tasks.reports.send_daily_summary"),
			("Monthly budget performance mail", "horizon_erp.tasks.reports.send_monthly_budget_reports"),
			("Self-test: flaky job", "horizon_erp.tasks.jobs.selftest_flaky")):
		log_doc = run_logged(job, method)
		log(f"+ {job}: {log_doc.status} ({log_doc.summary})")
	retry_failed_jobs()
	for r in frappe.get_all("Integration Log", filters={"retry_of": ("is", "set")}, fields=["job", "status"]):
		log(f"  retry of {r.job}: {r.status}")


STEPS = [
	("bank_masters", step_bank_masters),
	("purchase_invoices", step_purchase_invoices),
	("rcm_purchase", step_rcm_purchase),
	("customer_receipts", step_customer_receipts),
	("supplier_payments", step_supplier_payments),
	("bank_statement", step_bank_statement),
	("reconcile", step_reconcile),
	("budgets", step_budgets),
	("budget_overage", step_budget_overage),
	("net_settlement", step_net_settlement),
	("quality_deadline", step_quality_deadline),
	("migration_staging", step_migration_staging),
	("obsolete_stock", step_obsolete_stock),
	("api_client", step_api_client),
	("run_jobs", step_run_jobs),
]
