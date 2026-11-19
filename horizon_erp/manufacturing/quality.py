"""In-process quality: Job Card inspections, rework and non-conformance.

* A Job Card whose operation has an inspection template cannot be completed
  (submitted) without a submitted Quality Inspection that passed.
* Templates flagged "photo / video evidence required" (critical checks) need
  an evidence attachment on the QI, whatever the result.
* A failed / rework QI on a Job Card automatically:
    - opens a corrective Job Card (operation "HML Rework") on the same Work
      Order - ERPNext's native rework, which adds the rework cost to the WO,
    - flags the Work Order (Had Rework, Units Reworked) for first-pass yield,
    - logs a Non Conformance with the defect reason for root-cause analysis.
"""

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.constants import COMPANY

REWORK_OPERATION = "HML Rework"
QUALITY_PROCEDURE = "HML Manufacturing Quality Control"


def _company_of_job_card(name):
	return frappe.db.get_value("Job Card", name, "company")


def before_submit_job_card(doc, method=None):
	if doc.company != COMPANY or doc.get("is_corrective_job_card"):
		return
	if not doc.quality_inspection_template:
		return
	passed = frappe.db.exists(
		"Quality Inspection",
		{
			"reference_type": "Job Card",
			"reference_name": doc.name,
			"docstatus": 1,
			"hml_result": ("in", ["Pass", "Conditional Pass"]),
		},
	)
	if not passed:
		frappe.throw(
			_("Operation {0} has an inspection checkpoint ({1}). Submit a passing Quality Inspection for this Job Card first.").format(
				doc.operation, doc.quality_inspection_template
			),
			title=_("Inspection checkpoint"),
		)
	if not doc.quality_inspection:
		doc.quality_inspection = passed


def before_submit_qi_photo(doc, method=None):
	if doc.quality_inspection_template and frappe.get_cached_value(
		"Quality Inspection Template", doc.quality_inspection_template, "hml_photo_required"
	):
		has_file = doc.get("hml_evidence_photo") or frappe.db.exists(
			"File", {"attached_to_doctype": doc.doctype, "attached_to_name": doc.name}
		)
		if not has_file:
			frappe.throw(
				_("{0} is a critical check: attach a photo or video as evidence before submitting.").format(
					doc.quality_inspection_template
				)
			)


def on_submit_quality_inspection(doc, method=None):
	if doc.reference_type != "Job Card" or not doc.reference_name:
		return
	if _company_of_job_card(doc.reference_name) != COMPANY:
		return
	if doc.hml_result not in ("Fail", "Rework"):
		return
	jc = frappe.get_doc("Job Card", doc.reference_name)
	qty = flt(doc.hml_rejected_qty) or flt(doc.sample_size) or 1
	corrective = create_rework_job_card(jc, doc, qty)
	wo = frappe.get_doc("Work Order", jc.work_order)
	wo.db_set({"hml_has_rework": 1, "hml_rework_qty": flt(wo.hml_rework_qty) + qty}, update_modified=False)
	nc = log_non_conformance(doc, jc, qty, corrective)
	doc.add_comment("Comment", _("Rework Job Card {0} and Non Conformance {1} created.").format(corrective, nc))


def create_rework_job_card(jc, qi, qty):
	from erpnext.manufacturing.doctype.job_card.job_card import make_corrective_job_card

	cjc = make_corrective_job_card(jc.name, operation=REWORK_OPERATION, for_operation=jc.operation)
	cjc.for_quantity = qty
	# The mapper copies the failed operation's row id. Left in place, ERPNext
	# adds the rework qty to that operation's job-card total and rejects it
	# as over-production; the rework is a separate (corrective) operation.
	cjc.operation_id = None
	cjc.remarks = _("Rework after failed inspection {0}: {1}").format(qi.name, qi.hml_rejection_reason or "")
	cjc.flags.ignore_permissions = True
	cjc.insert()
	return cjc.name


def log_non_conformance(qi, jc, qty, corrective_job_card):
	if not frappe.db.exists("Quality Procedure", QUALITY_PROCEDURE):
		frappe.get_doc({"doctype": "Quality Procedure", "quality_procedure_name": QUALITY_PROCEDURE}).insert(ignore_permissions=True)
	nc = frappe.get_doc(
		{
			"doctype": "Non Conformance",
			"subject": f"{qi.hml_rejection_reason or 'Inspection failure'} - {jc.operation} - {jc.work_order}",
			"procedure": QUALITY_PROCEDURE,
			"status": "Open",
			"details": f"<p>Inspection {qi.name} on Job Card {jc.name} ({jc.operation}) failed. "
			f"Rework Job Card {corrective_job_card} raised for {qty} unit(s).</p><p>{qi.remarks or ''}</p>",
			"process_owner": jc.get("employee") and jc.employee[0].employee if jc.get("employee") else None,
			"hml_company": COMPANY,
			"hml_source": "Final Testing" if "Test" in (jc.operation or "") else "In-Process Inspection",
			"hml_item_code": jc.production_item,
			"hml_defect_reason": qi.hml_rejection_reason,
			"hml_defect_qty": qty,
			"hml_work_order": jc.work_order,
			"hml_job_card": jc.name,
			"hml_quality_inspection": qi.name,
		}
	)
	nc.insert(ignore_permissions=True)
	return nc.name
