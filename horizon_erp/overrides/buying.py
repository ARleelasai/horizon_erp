"""Purchase Order approval, supplier blacklist and receipt quality rules.

PO approval tiers (HML only, see workflow "HML Purchase Order Approval"):
	tier 1  < Rs 1,00,000            Dept Head
	tier 2  Rs 1,00,000 - 5,00,000   Dept Head -> Procurement Manager
	tier 3  > Rs 5,00,000            Dept Head -> Procurement Manager -> Finance Director
	        or blacklisted supplier  (always tier 3, whatever the amount)

Receipt flow: PO -> Purchase Receipt (draft = gate entry, goods in QC Hold)
-> Quality Inspection per line -> PR submit (= GRN, the only step that
updates stock). Failed quantity goes to the Rejected warehouse and is sent
back automatically with a Purchase Return plus a draft Debit Note.
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, time_diff_in_hours

from horizon_erp.constants import COMPANY, WH_REJECTED, is_hml

TIER_1_LIMIT = 100000
TIER_2_LIMIT = 500000
TIERS = {
	1: "1 - Dept Head",
	2: "2 - Dept Head + Procurement",
	3: "3 - Dept Head + Procurement + Finance Director",
}
INSPECTION_SLA_HOURS = 4


# ---------------------------------------------------------- Purchase Order


def approval_tier(doc):
	if doc.hml_supplier_blacklisted:
		return 3
	total = flt(doc.base_grand_total)
	if total > TIER_2_LIMIT:
		return 3
	if total >= TIER_1_LIMIT:
		return 2
	return 1


def validate_purchase_order(doc, method=None):
	if not is_hml(doc):
		return
	blacklisted = frappe.db.get_value("Supplier", doc.supplier, "hml_is_blacklisted")
	doc.hml_supplier_blacklisted = 1 if blacklisted else 0
	if blacklisted and not (doc.hml_blacklist_override_reason or "").strip():
		reason = frappe.db.get_value("Supplier", doc.supplier, "hml_blacklist_reason")
		frappe.throw(
			_("{0} is blacklisted: {1}<br><br>To buy anyway, enter a Blacklist Override Reason. The PO will need Finance Director approval.").format(
				frappe.bold(doc.supplier_name), reason or ""
			),
			title=_("Blacklisted supplier"),
		)
	doc.hml_approval_tier = TIERS[approval_tier(doc)]


def before_save_purchase_order(doc, method=None):
	if not is_hml(doc):
		return
	before = doc.get_doc_before_save()
	if not before or before.get("workflow_state") != doc.get("workflow_state"):
		doc.hml_state_since = now_datetime()


def on_update_purchase_order(doc, method=None):
	"""Audit hooks on workflow moves (docstatus 0 states)."""
	if not is_hml(doc):
		return
	before = doc.get_doc_before_save()
	old = before.get("workflow_state") if before else None
	new = doc.get("workflow_state")
	if old == new:
		return
	if new == "Rejected":
		comment = _last_comment(doc)
		doc.db_set("hml_rejection_comment", comment, update_modified=False)
		if doc.hml_supplier_blacklisted:
			_log_blacklist(doc, "Rejected")
	elif old in (None, "Draft", "Rejected") and new == "Pending Dept Head" and doc.hml_supplier_blacklisted:
		_log_blacklist(doc, "Override Requested")


def on_submit_purchase_order(doc, method=None):
	if is_hml(doc) and doc.hml_supplier_blacklisted:
		_log_blacklist(doc, "Approved by Finance Director")


def on_cancel_purchase_order(doc, method=None):
	if is_hml(doc) and doc.hml_supplier_blacklisted:
		_log_blacklist(doc, "Cancelled")


def _last_comment(doc):
	return frappe.db.get_value(
		"Comment",
		{"reference_doctype": doc.doctype, "reference_name": doc.name, "comment_type": "Comment"},
		"content",
		order_by="creation desc",
	)


def _log_blacklist(doc, event):
	frappe.get_doc(
		{
			"doctype": "Supplier Blacklist Exception",
			"supplier": doc.supplier,
			"purchase_order": doc.name,
			"company": doc.company,
			"amount": doc.base_grand_total,
			"event": event,
			"requested_by": doc.owner,
			"decided_by": frappe.session.user if event != "Override Requested" else None,
			"event_time": now_datetime(),
			"blacklist_reason": frappe.db.get_value("Supplier", doc.supplier, "hml_blacklist_reason"),
			"override_reason": doc.hml_blacklist_override_reason,
		}
	).insert(ignore_permissions=True)


def validate_blacklisted_without_po(doc, method=None):
	"""Purchase Receipt / Invoice: a blacklisted supplier is billable only via an approved PO."""
	if not is_hml(doc) or doc.get("is_return") or doc.get("is_internal_supplier"):
		return
	if not frappe.db.get_value("Supplier", doc.supplier, "hml_is_blacklisted"):
		return
	for row in doc.items:
		if not row.get("purchase_order"):
			frappe.throw(
				_("Row {0}: {1} is blacklisted. Receipts and invoices must reference a Purchase Order approved by the Finance Director.").format(
					row.idx, doc.supplier_name
				)
			)


# ------------------------------------------------------- Quality Inspection

RESULT_STATUS = {"Pass": "Accepted", "Conditional Pass": "Accepted", "Fail": "Rejected", "Rework": "Rejected"}


def validate_quality_inspection(doc, method=None):
	if doc.reference_type not in ("Purchase Receipt", "Purchase Invoice", "Job Card", "Stock Entry", "Delivery Note"):
		return
	company = frappe.db.get_value(doc.reference_type, doc.reference_name, "company") if doc.reference_name else None
	if company != COMPANY:
		return
	if doc.hml_result:
		doc.status = RESULT_STATUS[doc.hml_result]
		if doc.get("manual_inspection") is not None:
			doc.manual_inspection = 1  # our result drives status, not the readings
	if doc.reference_type == "Purchase Receipt" and doc.reference_name:
		pr = frappe.db.get_value("Purchase Receipt", doc.reference_name, ["supplier", "creation"], as_dict=True)
		doc.hml_supplier = pr.supplier
		doc.hml_received_at = doc.hml_received_at or pr.creation
	if doc.hml_result in ("Fail", "Rework"):
		if not doc.hml_rejection_reason:
			frappe.throw(_("Select a Rejection Reason for a failed inspection."))
		if not flt(doc.hml_rejected_qty):
			doc.hml_rejected_qty = flt(doc.sample_size) or 0
		if doc.docstatus == 1 or doc.flags.in_submit:
			_require_evidence(doc)


def before_submit_quality_inspection(doc, method=None):
	if not doc.get("hml_received_at"):
		return
	if not doc.hml_result:
		frappe.throw(_("Set the Result (Pass / Conditional Pass / Fail / Rework) before submitting."))
	if doc.hml_result in ("Fail", "Rework"):
		_require_evidence(doc)
	inspected_at = now_datetime()
	doc.hml_inspection_hours = round(time_diff_in_hours(inspected_at, doc.hml_received_at), 1)
	doc.hml_sla_met = 1 if doc.hml_inspection_hours <= INSPECTION_SLA_HOURS else 0


def _require_evidence(doc):
	has_file = doc.hml_evidence_photo or frappe.db.exists(
		"File", {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name}
	)
	if not has_file:
		frappe.throw(_("Attach a photo or document as evidence for the failed inspection."), title=_("Evidence required"))


# --------------------------------------------------------- Purchase Receipt


def before_validate_purchase_receipt(doc, method=None):
	"""Apply the inspection result to the receipt line (accepted / rejected split)."""
	if not is_hml(doc) or doc.is_return or doc.get("is_internal_supplier"):
		return
	for row in doc.items:
		if not row.quality_inspection:
			continue
		qi = frappe.db.get_value(
			"Quality Inspection", row.quality_inspection, ["hml_result", "hml_rejected_qty", "docstatus"], as_dict=True
		)
		if not qi or qi.hml_result not in ("Fail", "Rework"):
			continue
		received = flt(row.received_qty) or flt(row.qty) + flt(row.rejected_qty)
		rejected = min(flt(qi.hml_rejected_qty) or received, received)
		row.received_qty = received
		row.rejected_qty = rejected
		row.qty = received - rejected
		row.rejected_warehouse = row.rejected_warehouse or WH_REJECTED


def on_submit_purchase_receipt(doc, method=None):
	if not is_hml(doc) or doc.is_return or doc.get("is_internal_supplier"):
		return
	if any(flt(r.rejected_qty) for r in doc.items):
		return_rejected_goods(doc)


def return_rejected_goods(pr):
	"""Purchase Return for the rejected quantity + draft Debit Note for Accounts."""
	from erpnext.stock.doctype.purchase_receipt.purchase_receipt import (
		make_purchase_return_against_rejected_warehouse,
	)

	ret = make_purchase_return_against_rejected_warehouse(pr.name)
	ret.set_posting_time = 1
	ret.posting_date = pr.posting_date
	ret.posting_time = pr.posting_time
	ret.remarks = _("Auto return of goods rejected at incoming inspection ({0}).").format(pr.name)
	ret.flags.ignore_permissions = True
	ret.insert()
	ret.submit()

	debit = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"company": pr.company,
			"supplier": pr.supplier,
			"is_return": 1,
			"update_stock": 0,
			"posting_date": pr.posting_date,
			"set_posting_time": 1,
			"bill_no": f"DN-{pr.name}",
			"billing_address": pr.billing_address,
			"supplier_address": pr.supplier_address,
			"remarks": _(
				"Debit note for goods rejected at inspection on {0}. Submit once the supplier's invoice for the full dispatched quantity is booked; "
				"cancel if the supplier bills only the accepted quantity."
			).format(pr.name),
			"items": [
				{
					"item_code": r.item_code,
					"qty": -flt(r.rejected_qty),
					"rate": r.rate,
					"purchase_order": r.purchase_order,
					"po_detail": r.purchase_order_item,
					"cost_center": r.cost_center,
				}
				for r in pr.items
				if flt(r.rejected_qty)
			],
		}
	)
	debit.flags.ignore_permissions = True
	try:
		debit.insert()
		debit_name = debit.name
	except Exception:
		frappe.log_error(title=f"HML debit note draft failed for {pr.name}")
		debit_name = None
	pr.add_comment(
		"Comment",
		_("Rejected quantity returned via {0}{1}.").format(
			ret.name, _(" and draft Debit Note {0}").format(debit_name) if debit_name else ""
		),
	)
	return ret.name, debit_name
