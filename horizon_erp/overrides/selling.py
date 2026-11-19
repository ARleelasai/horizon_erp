"""Lead -> Opportunity -> Quotation -> Sales Order -> Delivery -> Invoice rules.

All rules apply only to Horizon Manufacturing Ltd (is_hml). Wired in hooks.py.

Pricing control (prevents ad-hoc pricing):
* Every item must have a price-list rate. No free-typed prices.
* Pricing Rules give the policy discount. Anything beyond that is a manual
  discount and needs a written reason.
* Effective discount (vs price list, incl. header discount) up to 15 % is
  auto-approved. Above 15 %, or any line priced below standard cost, the
  Quotation must go through the "HML Quotation Approval" workflow.
* A Sales Order above the threshold is accepted only when it comes from an
  approved Quotation and does not discount further.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate, now_datetime, nowdate

from horizon_erp.api.selling import get_item_planning_info
from horizon_erp.constants import is_hml

AUTO_APPROVE_LIMIT = 15.0
QUOTATION_VALIDITY_DAYS = 30
APPROVED_STATE = "Approved"


# ------------------------------------------------------------------ CRM


def validate_lead(doc, method=None):
	if not is_hml(doc):
		return
	missing = []
	if not (doc.lead_name or doc.company_name):
		missing.append(_("Person or Organisation name"))
	if not (doc.email_id or doc.mobile_no or doc.phone):
		missing.append(_("Email or Mobile"))
	for field, label in (("source", _("Source")), ("territory", _("Territory")), ("hml_product_interest", _("Product Interest"))):
		if not doc.get(field):
			missing.append(label)
	if missing:
		frappe.throw(_("Lead is missing: {0}").format(", ".join(missing)), title=_("Required for Horizon leads"))


def validate_opportunity(doc, method=None):
	if not is_hml(doc):
		return
	missing = [
		label
		for field, label in (
			("party_name", _("Lead / Customer")),
			("expected_closing", _("Expected Closing Date")),
			("sales_stage", _("Sales Stage")),
			("opportunity_amount", _("Opportunity Amount")),
		)
		if not doc.get(field)
	]
	if missing:
		frappe.throw(_("Opportunity is missing: {0}").format(", ".join(missing)), title=_("Required for Horizon opportunities"))
	if doc.status not in ("Lost", "Closed") and getdate(doc.expected_closing) < getdate(doc.transaction_date):
		frappe.throw(_("Expected Closing Date cannot be before the opportunity date"))


# ------------------------------------------------------------- pricing control


def _rule_discount(row):
	"""Discount % the applied Pricing Rules entitle this row to."""
	if not row.get("pricing_rules"):
		return 0.0
	try:
		rules = json.loads(row.pricing_rules)
	except Exception:
		rules = [r.strip() for r in str(row.pricing_rules).split(",") if r.strip()]
	total = 0.0
	for name in rules:
		rule = frappe.get_cached_value("Pricing Rule", name, ["rate_or_discount", "discount_percentage"], as_dict=True)
		if rule and rule.rate_or_discount == "Discount Percentage":
			total += flt(rule.discount_percentage)
	return total


def apply_pricing_control(doc):
	"""Compute discount fields; throw on ad-hoc pricing. Returns needs_approval."""
	list_value = policy_value = 0.0
	below_cost = False
	for row in doc.items:
		if not flt(row.price_list_rate):
			frappe.throw(
				_("Row {0}: {1} has no price in price list {2}. Add an Item Price before quoting; typed prices are not allowed.").format(
					row.idx, frappe.bold(row.item_code), doc.selling_price_list
				),
				title=_("No price list rate"),
			)
		list_value += flt(row.price_list_rate) * flt(row.qty)
		policy_value += flt(row.price_list_rate) * (1 - _rule_discount(row) / 100) * flt(row.qty)
		cost = flt(row.get("hml_unit_cost"))
		if cost and flt(row.rate) < cost:
			below_cost = True

	net_value = flt(doc.net_total)
	effective = (1 - net_value / list_value) * 100 if list_value else 0
	manual = max((policy_value - net_value) / list_value * 100, 0) if list_value else 0

	doc.hml_list_value = list_value
	doc.hml_effective_discount_pct = round(effective, 2)
	doc.hml_manual_discount_pct = round(manual, 2)
	doc.hml_below_cost = 1 if below_cost else 0
	doc.hml_needs_discount_approval = 1 if (effective > AUTO_APPROVE_LIMIT + 0.001 or below_cost) else 0

	if manual > 0.01 and not (doc.hml_discount_reason or "").strip():
		frappe.throw(
			_("A manual discount of {0}% beyond pricing rules was given. Enter the Discount Reason.").format(round(manual, 2)),
			title=_("Discount reason required"),
		)
	return doc.hml_needs_discount_approval


def apply_planning(doc, date_field):
	latest = None
	for row in doc.items:
		info = get_item_planning_info(row.item_code, row.stock_qty or row.qty, doc.company, doc.get(date_field))
		row.hml_available_qty = info["available_qty"]
		row.hml_bom = info["bom"]
		row.hml_unit_cost = info["unit_cost"]
		row.hml_lead_time_days = info["lead_time_days"]
		row.hml_estimated_delivery_date = info["estimated_delivery_date"]
		row.hml_estimate_basis = info["basis"]
		est = getdate(info["estimated_delivery_date"])
		latest = max(latest, est) if latest else est
	doc.hml_estimated_delivery_date = latest


# ------------------------------------------------------------------ Quotation


def validate_quotation(doc, method=None):
	if not is_hml(doc):
		return
	if not doc.valid_till:
		doc.valid_till = add_days(doc.transaction_date, QUOTATION_VALIDITY_DAYS)
	if date_diff(doc.valid_till, doc.transaction_date) > QUOTATION_VALIDITY_DAYS and not _has_role("HML Sales Manager", "HML Sales Director"):
		frappe.throw(
			_("Quotations are valid for at most {0} days. Only a Sales Manager can extend validity.").format(QUOTATION_VALIDITY_DAYS)
		)
	apply_planning(doc, "transaction_date")
	apply_pricing_control(doc)


def before_submit_quotation(doc, method=None):
	if not is_hml(doc):
		return
	if doc.hml_needs_discount_approval and doc.get("workflow_state") != APPROVED_STATE:
		frappe.throw(_("This quotation needs discount approval before it can be sent."))
	if doc.hml_needs_discount_approval:
		doc.hml_discount_approved_by = frappe.session.user
		doc.hml_discount_approved_on = now_datetime()


def on_submit_quotation(doc, method=None):
	if not is_hml(doc):
		return
	_log_discount(doc, "Approved" if doc.hml_needs_discount_approval else "Auto-approved")


def on_update_quotation(doc, method=None):
	"""Log workflow moves into / out of the approval queue (docstatus 0 states)."""
	if not is_hml(doc) or doc.docstatus != 0:
		return
	before = doc.get_doc_before_save()
	old_state = before.get("workflow_state") if before else None
	if doc.get("workflow_state") == old_state:
		return
	if doc.workflow_state == "Pending Discount Approval":
		_log_discount(doc, "Requested")
	elif doc.workflow_state == "Rejected":
		_log_discount(doc, "Rejected")


def _log_discount(doc, decision):
	comment = None
	if decision in ("Approved", "Rejected"):
		comment = frappe.db.get_value(
			"Comment",
			{"reference_doctype": doc.doctype, "reference_name": doc.name, "comment_type": "Comment"},
			"content",
			order_by="creation desc",
		)
	frappe.get_doc(
		{
			"doctype": "Discount Approval Log",
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
			"customer": doc.get("party_name") or doc.get("customer"),
			"company": doc.company,
			"decision": decision,
			"decided_by": frappe.session.user,
			"decided_on": now_datetime(),
			"list_value": doc.hml_list_value,
			"net_value": doc.net_total,
			"effective_discount_pct": doc.hml_effective_discount_pct,
			"manual_discount_pct": doc.hml_manual_discount_pct,
			"below_cost": doc.hml_below_cost,
			"reason": doc.hml_discount_reason,
			"comment": comment,
		}
	).insert(ignore_permissions=True)


def _has_role(*roles):
	user_roles = set(frappe.get_roles())
	return bool(user_roles.intersection(roles)) or "System Manager" in user_roles


# ---------------------------------------------------------------- Sales Order


def validate_sales_order(doc, method=None):
	if not is_hml(doc):
		return
	if not doc.po_no and not doc.get("is_internal_customer"):
		frappe.throw(_("Customer's Purchase Order No is required (Horizon order acceptance rule)."))
	for row in doc.items:
		if row.prevdoc_docname:
			q = frappe.db.get_value("Quotation", row.prevdoc_docname, ["valid_till", "status"], as_dict=True)
			if q and q.valid_till and getdate(q.valid_till) < getdate(doc.transaction_date):
				frappe.throw(
					_("Row {0}: Quotation {1} expired on {2}. Re-quote before accepting the order.").format(
						row.idx, row.prevdoc_docname, frappe.format(q.valid_till, "Date")
					)
				)
	apply_planning(doc, "transaction_date")
	apply_pricing_control(doc)
	doc.hml_delivery_risk = 1 if doc.delivery_date and doc.hml_estimated_delivery_date and getdate(doc.delivery_date) < getdate(doc.hml_estimated_delivery_date) else 0


CREDIT_OVERRIDE_ROLES = ("HML Finance Director", "Accounts Manager")


def check_credit_limit(doc):
	"""Credit control for Horizon (the DMS credit check on this site only runs
	for companies with DMS settings, so Horizon enforces its own).

	Exposure = posted receivable + open orders not yet invoiced + this order.
	Same rule every day of the month: the month-end sales push is exactly
	when credit discipline matters. Beyond the limit only the Finance
	Director / Accounts Manager can submit, with a written reason (logged).
	"""
	if doc.get("is_internal_customer"):
		return
	limit = frappe.db.get_value(
		"Customer Credit Limit", {"parent": doc.customer, "company": doc.company}, ["credit_limit", "bypass_credit_limit_check"], as_dict=True
	)
	if not limit or not flt(limit.credit_limit) or limit.bypass_credit_limit_check:
		return
	outstanding = flt(frappe.db.sql(
		"select sum(debit - credit) from `tabGL Entry` where company = %s and party_type = 'Customer' and party = %s and is_cancelled = 0",
		(doc.company, doc.customer))[0][0])
	open_orders = flt(frappe.db.sql(
		"""select sum(base_grand_total * (100 - per_billed) / 100) from `tabSales Order`
		where company = %s and customer = %s and docstatus = 1 and status not in ('Closed', 'Completed') and name != %s""",
		(doc.company, doc.customer, doc.name))[0][0])
	exposure = outstanding + open_orders + flt(doc.base_grand_total)
	doc.hml_credit_exposure = exposure
	if exposure <= flt(limit.credit_limit):
		return
	msg = _("Credit limit {0}; exposure would be {1} (receivable {2} + open orders {3} + this order {4}).").format(
		frappe.format(limit.credit_limit, "Currency"), frappe.format(exposure, "Currency"), frappe.format(outstanding, "Currency"),
		frappe.format(open_orders, "Currency"), frappe.format(doc.base_grand_total, "Currency"))
	if _has_role(*CREDIT_OVERRIDE_ROLES) and (doc.hml_credit_override_reason or "").strip():
		doc.add_comment("Comment", _("Credit limit overridden by {0}: {1}. {2}").format(frappe.session.user, doc.hml_credit_override_reason, msg))
		return
	frappe.throw(msg + "<br>" + _("Collect payment, reduce the order, or ask Finance to approve with a Credit Limit Override Reason."),
		title=_("Credit limit exceeded"))


def before_submit_sales_order(doc, method=None):
	if not is_hml(doc):
		return
	check_credit_limit(doc)
	if not doc.hml_needs_discount_approval:
		return
	quotations = {row.prevdoc_docname for row in doc.items}
	if None in quotations or "" in quotations or not quotations:
		frappe.throw(
			_("Effective discount {0}% exceeds {1}% (or a line is below cost). Raise a Quotation and get it approved first.").format(
				doc.hml_effective_discount_pct, AUTO_APPROVE_LIMIT
			),
			title=_("Discount approval required"),
		)
	for q in quotations:
		if frappe.db.get_value("Quotation", q, "workflow_state") != APPROVED_STATE:
			frappe.throw(_("Quotation {0} is not approved.").format(q))
	quoted = {
		r.name: flt(r.rate)
		for r in frappe.get_all("Quotation Item", filters={"parent": ("in", list(quotations))}, fields=["name", "rate"])
	}
	for row in doc.items:
		if row.quotation_item and flt(row.rate) < quoted.get(row.quotation_item, 0) - 0.01:
			frappe.throw(_("Row {0}: rate is lower than the approved quotation rate.").format(row.idx))
	doc.hml_discount_approved_by = frappe.db.get_value("Quotation", next(iter(quotations)), "hml_discount_approved_by")
	doc.hml_discount_approved_on = now_datetime()


# --------------------------------------------------------------- Delivery Note


def before_validate_delivery_note(doc, method=None):
	"""Deliveries carry the Sales Order price, always.

	ERPNext re-runs pricing rules when a DN is mapped from a Pick List. A
	partial shipment then falls below the bulk-quantity threshold and the DN
	(and the auto-invoice) is priced higher than the order: the customer is
	over-billed and ERPNext raises an over-billing error on the last invoice.
	"""
	if not is_hml(doc) or doc.is_return:
		return
	so_rows = [r.so_detail for r in doc.items if r.so_detail]
	if not so_rows:
		return
	doc.ignore_pricing_rule = 1
	prices = {
		r.name: r
		for r in frappe.get_all(
			"Sales Order Item",
			filters={"name": ("in", so_rows)},
			fields=["name", "price_list_rate", "discount_percentage", "discount_amount", "rate"],
		)
	}
	for row in doc.items:
		so = prices.get(row.so_detail)
		if so:
			row.price_list_rate = so.price_list_rate
			row.discount_percentage = so.discount_percentage
			row.discount_amount = so.discount_amount
			row.rate = so.rate
			# Cleared on purpose: with ignore_pricing_rule set, ERPNext strips
			# rule-derived discounts from rows that still list their rules,
			# which would re-price the auto-invoice at full list price.
			row.pricing_rules = None


def validate_delivery_note(doc, method=None):
	if not is_hml(doc) or doc.is_return or doc.get("is_internal_customer"):
		return
	deviation = False
	for row in doc.items:
		if not row.against_sales_order:
			frappe.throw(
				_("Row {0}: {1} is not linked to a Sales Order. Horizon deliveries are made only against confirmed orders.").format(
					row.idx, row.item_code
				)
			)
		if row.so_detail:
			ordered, delivered = frappe.db.get_value("Sales Order Item", row.so_detail, ["qty", "delivered_qty"])
			if abs(flt(row.qty) - (flt(ordered) - flt(delivered))) > 0.0001:
				deviation = True
	doc.hml_has_deviation = 1 if deviation else 0


def before_submit_delivery_note(doc, method=None):
	if not is_hml(doc) or doc.is_return or doc.get("is_internal_customer"):
		return
	stock_rows = [r for r in doc.items if frappe.get_cached_value("Item", r.item_code, "is_stock_item")]
	if stock_rows and not doc.pick_list:
		frappe.throw(
			_("Create the Delivery Note from a Pick List (packing step: Sales Order -> Pick List -> Delivery Note)."),
			title=_("Packing step missing"),
		)
	if doc.hml_has_deviation and not (doc.hml_deviation_notes or "").strip():
		frappe.throw(_("Delivered quantity differs from the open Sales Order quantity. Enter Deviation Notes."))


def on_submit_delivery_note(doc, method=None):
	"""Invoice automatically, only once goods have left (DN submitted)."""
	if not is_hml(doc) or doc.is_return or doc.get("is_internal_customer"):
		return
	if frappe.flags.hml_skip_auto_invoice:
		return
	create_invoice_from_delivery_note(doc)


def create_invoice_from_delivery_note(dn):
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

	frappe.db.savepoint("hml_auto_invoice")
	try:
		si = make_sales_invoice(dn.name)
		si.update_stock = 0
		si.set_posting_time = 1
		si.posting_date = dn.posting_date
		si.due_date = None
		si.flags.ignore_permissions = True
		si.insert()
		si.submit()
		dn.add_comment("Comment", _("Sales Invoice {0} created automatically on delivery.").format(si.name))
		return si.name
	except Exception:
		if frappe.flags.hml_seed:
			import traceback

			traceback.print_exc()
		frappe.db.rollback(save_point="hml_auto_invoice")
		frappe.log_error(title=f"HML auto-invoice failed for {dn.name}")
		dn.add_comment(
			"Comment",
			_("Automatic invoicing failed; create the Sales Invoice manually. See Error Log for details."),
		)


# --------------------------------------------------------------- Sales Invoice


def validate_sales_invoice(doc, method=None):
	if not is_hml(doc) or doc.is_return or doc.get("is_internal_customer") or doc.is_pos:
		return
	if cint(doc.update_stock):
		frappe.throw(
			_("Horizon invoices are raised after delivery. Untick Update Stock and create the invoice from the Delivery Note."),
			title=_("Invoice before delivery not allowed"),
		)
	for row in doc.items:
		if not frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			continue  # services, project milestones
		if not row.delivery_note and not _bill_and_hold_allowed(doc, row):
			frappe.throw(
				_("Row {0}: {1} has not been delivered. Invoice only from a submitted Delivery Note.").format(
					row.idx, row.item_code
				),
				title=_("Invoice before delivery not allowed"),
			)


def _bill_and_hold_allowed(doc, row):
	"""Phase 6: an approved Quality Deadline Decision may allow invoice-now-ship-later."""
	if not frappe.db.exists("DocType", "Quality Deadline Decision"):
		return False
	return bool(
		frappe.db.exists(
			"Quality Deadline Decision",
			{"sales_order": row.sales_order, "decision": "Invoice Now, Ship Later", "docstatus": 1},
		)
	)
