"""Phase 4 - Manufacturing for Horizon Manufacturing Ltd.

Lines A and B, operations with inspection checkpoints, two 3-level products
(HX-500 press, CX-200 conveyor) with revision-controlled BOMs and routings,
work orders executed end to end with job cards and inspections (including a
failed weld inspection, rework job card and non-conformance), a production
audit below 70 that blocks completion, a capacity conflict resolved by a
recorded decision, and a make-to-stock work order raised from a sales order.
"""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, get_datetime, getdate

from horizon_erp.constants import (
	ADDRESS_MUMBAI,
	COMPANY,
	WH_FG,
	WH_MUMBAI,
	WH_RM,
	WH_WIP,
)
from horizon_erp.setup.seed.phase1 import customer_name, supplier_name, user_email
from horizon_erp.setup.seed.phase2 import _deliver, so_name
from horizon_erp.setup.seed.utils import get_or_insert, log

QI_USER = user_email("ramesh.iyer")
OPS_HEAD = user_email("priya.nair")
SALES_EXEC = user_email("rohan.mehta")
LINE_A = "HML Line A"
LINE_B = "HML Line B"


def admin():
	frappe.set_user("Administrator")


# ------------------------------------------------------------------ masters

WORKSTATIONS = {
	LINE_A: dict(electricity=180, consumable=60, rent=120, labour=450, downtime=10, setup=45,
		description="Heavy line: presses and welded frames. 2 shifts, 06:00-22:00."),
	LINE_B: dict(electricity=140, consumable=50, rent=100, labour=430, downtime=8, setup=30,
		description="Light line: conveyors and sub-assemblies. 2 shifts, 06:00-22:00."),
}

OP_PARAMETERS = {
	"Weld Bead Visual (porosity / undercut)": (0, None, None, "None visible"),
	"Fillet Leg Size (mm)": (1, 6, 8, None),
	"Penetration Depth (mm)": (1, 3, 10, None),
	"Dry Film Thickness (microns)": (1, 80, 120, None),
	"Cross-cut Adhesion Class": (0, None, None, "0 or 1"),
	"Bolt Torque M12 (Nm)": (1, 75, 85, None),
	"Alignment / Run-out": (0, None, None, "Within 0.5 mm"),
	"Pressure Hold 250 bar 10 min": (0, None, None, "No drop"),
	"Rated Load Test": (0, None, None, "Pass"),
	"Noise at 1 m (dB)": (1, 0, 80, None),
}

OP_TEMPLATES = {
	# template: (params, photo_required)
	"HML Op - Weld Inspection": (["Weld Bead Visual (porosity / undercut)", "Fillet Leg Size (mm)", "Penetration Depth (mm)"], 1),
	"HML Op - Paint Inspection": (["Dry Film Thickness (microns)", "Cross-cut Adhesion Class"], 0),
	"HML Op - Assembly Inspection": (["Bolt Torque M12 (Nm)", "Alignment / Run-out"], 0),
	"HML Op - Final Test": (["Pressure Hold 250 bar 10 min", "Rated Load Test", "Noise at 1 m (dB)"], 1),
}

OPERATIONS = {
	"HML Cutting": (LINE_B, None, 0),
	"HML Welding": (LINE_A, "HML Op - Weld Inspection", 0),
	"HML Painting": (LINE_B, "HML Op - Paint Inspection", 0),
	"HML Assembly": (LINE_A, "HML Op - Assembly Inspection", 0),
	"HML Testing": (LINE_A, "HML Op - Final Test", 0),
	"HML Rework": (LINE_A, None, 1),
}


def step_masters():
	# sub-assemblies are stored in stores (RM) so the final-assembly WO can draw them
	for code in ("SA-HX-FRAME", "SA-HX-HPU", "SA-HX-CTRL", "SA-CX-FRAME", "SA-CX-DRIVE"):
		frappe.db.set_value("Item Default", {"parent": code, "company": COMPANY}, "default_warehouse", WH_RM)
	for name, w in WORKSTATIONS.items():
		get_or_insert(
			"Workstation",
			name,
			{
				"workstation_name": name,
				"description": w["description"],
				"hour_rate_electricity": w["electricity"],
				"hour_rate_consumable": w["consumable"],
				"hour_rate_rent": w["rent"],
				"hour_rate_labour": w["labour"],
				"production_capacity": 3,  # cutting, welding and paint/assembly stations run in parallel
				"hml_downtime_pct": w["downtime"],
				"hml_setup_time_mins": w["setup"],
				# morning 06-14 + afternoon 14-22 shifts as one window (ERPNext rejects touching rows)
				"working_hours": [{"start_time": "06:00:00", "end_time": "22:00:00", "enabled": 1}],
			},
		)
	from horizon_erp.setup.seed.phase3 import PARAMETERS

	for p in OP_PARAMETERS:
		get_or_insert("Quality Inspection Parameter", p, {"parameter": p, "description": p})
	for name, (params, photo) in OP_TEMPLATES.items():
		rows = []
		for p in params:
			numeric, mn, mx, value = OP_PARAMETERS[p]
			rows.append({"specification": p, "numeric": numeric, "min_value": mn, "max_value": mx, "value": value})
		get_or_insert(
			"Quality Inspection Template",
			name,
			{"quality_inspection_template_name": name, "hml_photo_required": photo, "item_quality_inspection_parameter": rows},
		)
	for name, (ws, template, corrective) in OPERATIONS.items():
		get_or_insert(
			"Operation",
			name,
			{"workstation": ws, "quality_inspection_template": template, "is_corrective_operation": corrective,
				"description": name.replace("HML ", "")},
			set_name=name,
		)
	get_or_insert(
		"Quality Procedure",
		"HML Manufacturing Quality Control",
		{"quality_procedure_name": "HML Manufacturing Quality Control"},
	)
	assert PARAMETERS  # incoming parameters exist (phase 3)


# --------------------------------------------------- hydraulic oil (batch item)


def step_hydraulic_oil():
	"""Batch-tracked receipt: needed by the HX-500 power unit."""
	if frappe.db.exists("Batch", {"item": "RM-HYD-OIL-68"}):
		return
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"title": "PO9 - HML seed",
			"supplier": supplier_name("hydrotech"),
			"company": COMPANY,
			"transaction_date": "2026-10-14",
			"schedule_date": "2026-10-20",
			"billing_address": ADDRESS_MUMBAI,
			"set_warehouse": WH_RM,
			"items": [{"item_code": "RM-HYD-OIL-68", "qty": 300, "rate": 160, "schedule_date": "2026-10-20", "warehouse": WH_RM}],
		}
	)
	frappe.set_user(user_email("pooja.shah"))
	po.insert()
	apply_workflow(po, "Submit for Approval")
	frappe.set_user(user_email("suresh.patil"))
	po.reload()
	apply_workflow(po, "Approve")
	admin()
	batch = frappe.get_doc(
		{"doctype": "Batch", "item": "RM-HYD-OIL-68", "custom_batch_no": "-HO2610", "manufacturing_date": "2026-10-10"}
	)
	batch.insert(ignore_permissions=True)
	pr = make_purchase_receipt(po.name)
	pr.set_posting_time = 1
	pr.posting_date = "2026-10-20"
	pr.posting_time = "11:00:00"
	for row in pr.items:
		row.use_serial_batch_fields = 1
		row.batch_no = batch.name
	pr.insert(ignore_permissions=True)
	qi = frappe.get_doc(
		{
			"doctype": "Quality Inspection",
			"inspection_type": "Incoming",
			"reference_type": "Purchase Receipt",
			"reference_name": pr.name,
			"child_row_reference": pr.items[0].name,
			"item_code": "RM-HYD-OIL-68",
			"batch_no": batch.name,
			"inspected_by": QI_USER,
			"sample_size": 1,
			"report_date": "2026-10-20",
			"quality_inspection_template": "HML Incoming - Paint and Consumables",
			"hml_result": "Pass",
			"manual_inspection": 1,
		}
	)
	qi.get_item_specification_details()
	for r in qi.readings:
		r.status = "Accepted"
		r.reading_value = r.value
		if r.numeric:
			r.reading_1 = str(r.min_value + 5)
	qi.insert(ignore_permissions=True)
	qi.submit()
	qi.db_set({"hml_received_at": "2026-10-20 11:00:00", "hml_inspection_hours": 2.0, "hml_sla_met": 1})
	pr.reload()
	pr.submit()
	log(f"+ Hydraulic oil: PO {po.name}, batch {batch.name}, GRN {pr.name}")


def step_seal_kits():
	"""Mumbai sent all its seal kits to Delhi in September; top up for the HX-500 rev 2 BOM."""
	from horizon_erp.setup.seed import phase3

	if phase3.po_name("PO10"):
		return
	phase3.POS["PO10"] = ("hydrotech", "2026-10-26", "2026-11-06", [("SP-SEAL-KIT-HX", 20, 2200)], "Urgent", "approve", {})
	phase3.RECEIPTS.append(("PO10", "2026-11-06", "14:00:00", [("SP-SEAL-KIT-HX", "Pass", 0, None, None)], 2.0))
	only = {k: v for k, v in phase3.POS.items() if k == "PO10"}
	saved_pos, saved_rec = phase3.POS, phase3.RECEIPTS
	phase3.POS = only
	phase3.RECEIPTS = [r for r in saved_rec if r[0] == "PO10"]
	try:
		phase3.step_purchase_orders()
		phase3.step_receipts()
	finally:
		phase3.POS, phase3.RECEIPTS = saved_pos, saved_rec
	# put-away: spares live in the finished-goods store
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"company": COMPANY,
			"set_posting_time": 1,
			"posting_date": "2026-11-06",
			"posting_time": "16:00:00",
			"items": [{"item_code": "SP-SEAL-KIT-HX", "qty": 20, "s_warehouse": WH_RM, "t_warehouse": WH_FG}],
		}
	)
	se.insert(ignore_permissions=True)
	se.submit()
	log(f"  seal kits put away to FG store via {se.name}")


# --------------------------------------------------------------------- BOMs

# item: (rev reason, notes, line, ops [(operation, minutes)], rows [(item, qty)])
BOMS = [
	("SA-HX-FRAME", "Initial Release", None, LINE_A,
		[("HML Cutting", 60), ("HML Welding", 150), ("HML Painting", 60)],
		[("RM-MS-PLATE-10", 420), ("RM-MS-CHANNEL-100", 260), ("RM-WELD-E7018", 12), ("RM-PAINT-EPOXY", 8), ("RM-BOLT-M12", 40)]),
	("SA-HX-HPU", "Initial Release", None, LINE_A,
		[("HML Assembly", 90), ("HML Testing", 30)],
		[("CMP-CYL-100", 2), ("CMP-PUMP-GP20", 1), ("CMP-MOTOR-5HP", 1), ("CMP-MANIFOLD-HX", 1), ("RM-HYD-OIL-68", 60), ("RM-BOLT-M12", 16)]),
	("SA-HX-CTRL", "Initial Release", None, LINE_A,
		[("HML Assembly", 60)],
		[("CMP-PLC-24", 1), ("RM-BOLT-M12", 8)]),
	("SA-CX-FRAME", "Initial Release", None, LINE_B,
		[("HML Cutting", 30), ("HML Welding", 90), ("HML Painting", 30)],
		[("RM-MS-CHANNEL-100", 180), ("RM-MS-PLATE-10", 60), ("RM-WELD-E7018", 5), ("RM-PAINT-EPOXY", 4), ("RM-BOLT-M12", 30)]),
	("SA-CX-DRIVE", "Initial Release", None, LINE_B,
		[("HML Assembly", 60)],
		[("CMP-MOTOR-2HP", 1), ("CMP-GEARBOX-30", 1), ("CMP-BRG-6205", 4)]),
	("HX-500", "Initial Release", None, LINE_A,
		[("HML Assembly", 180), ("HML Testing", 90)],
		[("SA-HX-FRAME", 1), ("SA-HX-HPU", 1), ("SA-HX-CTRL", 1), ("RM-BOLT-M12", 24)]),
	("HX-500", "Design Change", "ECN-2026-014: a spare cylinder seal kit ships with every press (field failure analysis, Q2). "
		"Adds SP-SEAL-KIT-HX x1 to the top level.", LINE_A,
		[("HML Assembly", 180), ("HML Testing", 90)],
		[("SA-HX-FRAME", 1), ("SA-HX-HPU", 1), ("SA-HX-CTRL", 1), ("RM-BOLT-M12", 24), ("SP-SEAL-KIT-HX", 1)]),
	("CX-200", "Initial Release", None, LINE_B,
		[("HML Assembly", 120), ("HML Testing", 30)],
		[("SA-CX-FRAME", 1), ("SA-CX-DRIVE", 1), ("CMP-ROLLER-50", 24), ("RM-BELT-PVC-600", 13), ("RM-BOLT-M12", 20)]),
]


def step_boms():
	for item, reason, notes, line, ops, rows in BOMS:
		existing = frappe.get_all("BOM", filters={"item": item, "docstatus": 1, "hml_revision_reason": reason}, pluck="name")
		if existing:
			continue
		routing_name = f"HML {item} Routing"
		if not frappe.db.exists("Routing", routing_name):
			frappe.get_doc(
				{
					"doctype": "Routing",
					"routing_name": routing_name,
					"operations": [
						{"operation": op, "workstation": line if op != "HML Cutting" else LINE_B, "time_in_mins": mins, "sequence_id": i + 1}
						for i, (op, mins) in enumerate(ops)
					],
				}
			).insert(ignore_permissions=True)
		bom = frappe.get_doc(
			{
				"doctype": "BOM",
				"item": item,
				"company": COMPANY,
				"quantity": 1,
				"is_active": 1,
				"is_default": 1,
				"with_operations": 1,
				"routing": routing_name,
				"rm_cost_as_per": "Valuation Rate",
				"hml_revision_reason": reason,
				"hml_revision_notes": notes,
				"hml_ecn_no": "ECN-2026-014" if reason == "Design Change" else None,
				"operations": [
					{"operation": op, "workstation": line if op != "HML Cutting" else LINE_B, "time_in_mins": mins, "sequence_id": i + 1}
					for i, (op, mins) in enumerate(ops)
				],
				"items": [{"item_code": c, "qty": q} for c, q in rows],
			}
		)
		bom.insert(ignore_permissions=True)
		bom.submit()
		log(f"+ BOM {bom.name} rev {bom.hml_revision_no} ({reason}) cost Rs {bom.total_cost:,.0f}")


# -------------------------------------------------------------- execution


def _wo(item, qty, start, line=None, sales_order=None, **extra):
	bom = frappe.db.get_value("Item", item, "default_bom")
	wo = frappe.get_doc(
		{
			"doctype": "Work Order",
			"company": COMPANY,
			"production_item": item,
			"bom_no": bom,
			"qty": qty,
			"use_multi_level_bom": 0,
			"sales_order": sales_order,
			"wip_warehouse": WH_WIP,
			# sub-assemblies go back to stores, where the final assembly WO draws them
			"fg_warehouse": WH_FG if item in ("HX-500", "CX-200") else WH_RM,
			"source_warehouse": WH_RM,
			"planned_start_date": f"{start} 06:00:00",
			"hml_production_line": line,
			**extra,
		}
	)
	if sales_order:
		wo.sales_order_item = frappe.db.get_value("Sales Order Item", {"parent": sales_order, "item_code": item}, "name")
	wo.get_items_and_operations_from_bom()  # what the form does; server insert alone skips operations
	wo.insert(ignore_permissions=True)
	wo.submit()
	return wo


def _stock_entry(wo, purpose, qty, when):
	se = frappe.get_doc(make_stock_entry(wo.name, purpose, qty))
	se.set_posting_time = 1
	se.posting_date = getdate(when)
	se.posting_time = str(get_datetime(when).time())
	se.inspection_required = 0
	se.insert(ignore_permissions=True)
	se.submit()
	return se


def _inspect_job_card(jc, result, when, rejected_qty=None, reason=None, remarks=None):
	qi = frappe.get_doc(
		{
			"doctype": "Quality Inspection",
			"inspection_type": "In Process",
			"reference_type": "Job Card",
			"reference_name": jc.name,
			"item_code": jc.production_item,
			"sample_size": jc.for_quantity,
			"report_date": getdate(when),
			"inspected_by": QI_USER,
			"quality_inspection_template": jc.quality_inspection_template,
			"hml_result": result,
			"hml_rejected_qty": rejected_qty,
			"hml_rejection_reason": reason,
			"hml_evidence_photo": "/assets/frappe/images/default-avatar.png",
			"remarks": remarks,
			"manual_inspection": 1,
		}
	)
	qi.get_item_specification_details()
	for r in qi.readings:
		r.status = "Accepted" if result in ("Pass", "Conditional Pass") else "Rejected"
		r.reading_value = r.value
		if r.numeric:
			r.reading_1 = str((r.min_value + r.max_value) / 2) if result == "Pass" else str(r.min_value - 1)
	qi.insert(ignore_permissions=True)
	qi.submit()
	return qi


def _complete_job_card(name, start, minutes):
	jc = frappe.get_doc("Job Card", name)
	jc.append(
		"time_logs",
		{
			"from_time": get_datetime(start),
			"to_time": frappe.utils.add_to_date(get_datetime(start), minutes=minutes),
			"completed_qty": jc.for_quantity,
		},
	)
	jc.save(ignore_permissions=True)
	return jc


def run_work_order(wo, day, finish=True, fail_operation=None):
	"""Transfer materials, run every job card (with inspections), manufacture."""
	_stock_entry(wo, "Material Transfer for Manufacture", wo.qty, f"{day} 06:30:00")
	t = get_datetime(f"{day} 07:00:00")
	for jc_name in frappe.get_all("Job Card", filters={"work_order": wo.name, "docstatus": 0, "is_corrective_job_card": 0},
			order_by="sequence_id asc, creation asc", pluck="name"):
		jc = _complete_job_card(jc_name, t, frappe.db.get_value("Job Card", jc_name, "time_required") or 60)
		t = frappe.utils.add_to_date(t, minutes=(jc.time_required or 60) + 15)
		if jc.quality_inspection_template:
			if fail_operation and jc.operation == fail_operation:
				_inspect_job_card(jc, "Rework", t, rejected_qty=jc.for_quantity, reason="Weld defect - porosity / undercut",
					remarks="Porosity on the main frame fillet weld, 3 locations; undercut 1.2 mm on base plate joint.")
				cjc_name = frappe.db.get_value("Job Card", {"work_order": wo.name, "is_corrective_job_card": 1, "docstatus": 0})
				cjc = _complete_job_card(cjc_name, t, 120)
				cjc.submit()
				t = frappe.utils.add_to_date(t, minutes=135)
				log(f"  rework job card {cjc.name} for {jc.operation}")
			_inspect_job_card(jc, "Pass", t)
		jc.reload()
		jc.submit()
	if finish:
		_stock_entry(wo, "Manufacture", wo.qty, frappe.utils.add_to_date(t, minutes=30))
	wo.reload()
	log(f"+ WO {wo.name} {wo.production_item} x{wo.qty} on {wo.hml_production_line}: {wo.status}")
	return wo


def wo_for(item, sales_order=None, title=None):
	filters = {"production_item": item, "company": COMPANY, "docstatus": 1}
	if sales_order:
		filters["sales_order"] = sales_order
	if title:
		filters["description"] = title
	return frappe.db.get_value("Work Order", filters)


def step_cx200_for_so1():
	so1 = so_name("SO1")
	if wo_for("CX-200", so1):
		return
	frame = run_work_order(_wo("SA-CX-FRAME", 2, "2026-11-02", LINE_B, description="CX-200 lot 1 frames"), "2026-11-02")
	drive = run_work_order(_wo("SA-CX-DRIVE", 2, "2026-11-03", LINE_B, description="CX-200 lot 1 drives"), "2026-11-03")
	fg = run_work_order(_wo("CX-200", 2, "2026-11-04", LINE_B, sales_order=so1), "2026-11-04")
	assert frame and drive and fg
	# Serialised goods: the Pick List reserves serials with today's timestamp,
	# so a back-dated Delivery Note would sit "before" its own pick. Ship today.
	_deliver("SO1", frappe.utils.nowdate(), parent_warehouse=WH_MUMBAI,
		notes="Delivered 7 weeks late: production started only after frame steel arrived (PO1).")


def step_hx500_for_so3():
	so3 = so_name("SO3")
	if wo_for("HX-500", so3):
		return
	run_work_order(_wo("SA-HX-FRAME", 1, "2026-11-09", LINE_A, description="HX-500 SO3 frame"), "2026-11-09", fail_operation="HML Welding")
	run_work_order(_wo("SA-HX-HPU", 1, "2026-11-10", LINE_A, description="HX-500 SO3 power unit"), "2026-11-10")
	run_work_order(_wo("SA-HX-CTRL", 1, "2026-11-11", LINE_A, description="HX-500 SO3 control panel"), "2026-11-11")
	wo = _wo(
		"HX-500", 1, "2026-11-12", LINE_A, sales_order=so3,
		hml_capacity_decision="Delay Delivery (customer agreed)",
		hml_capacity_decision_note="Order was taken with 30 Oct promise before the BOM existed; new date 28 Nov agreed with Gujarat Pump Works (Amit, 4 Nov).",
	)
	_stock_entry(wo, "Material Transfer for Manufacture", 1, "2026-11-12 06:30:00")
	asm = frappe.db.get_value("Job Card", {"work_order": wo.name, "operation": "HML Assembly"})
	jc = _complete_job_card(asm, "2026-11-12 07:00:00", 180)
	_inspect_job_card(jc, "Pass", "2026-11-12 10:30:00")
	jc.reload()
	jc.submit()
	log(f"+ WO {wo.name} HX-500 for SO3 in progress (assembly done, testing pending)")


def step_production_audits():
	if frappe.db.exists("Production Audit", {"docstatus": 1}):
		return
	hx = wo_for("HX-500", so_name("SO3"))
	cx = wo_for("CX-200", so_name("SO1"))
	frame = wo_for("SA-HX-FRAME", title="HX-500 SO3 frame")
	audits = [
		(cx, "2026-11-04", 88, "<p>5S good, torque records complete, serials engraved. Minor: two missing tool shadow-board outlines.</p>"),
		(frame, "2026-11-09", 74, "<p>Welder WPS card not displayed at station; post-rework weld acceptable. Fume extraction hose damaged.</p>"),
		(hx, "2026-11-13", 62,
			"<p><b>Hydraulic hose routing rubs on frame edge</b> (no grommet), loose fitting on return line found at pre-test, "
			"assembly checklist not signed for torque step 7. Unit must not go to test until reworked.</p>"),
	]
	frappe.set_user(QI_USER)
	for wo, date, score, findings in audits:
		pa = frappe.get_doc(
			{
				"doctype": "Production Audit",
				"work_order": wo,
				"audit_date": date,
				"inspector": QI_USER,
				"audit_score": score,
				"findings": findings,
				"photo_1": "/assets/frappe/images/default-avatar.png",
			}
		)
		pa.insert()
		apply_workflow(pa, "Submit")
		pa.reload()
		log(f"+ Production Audit {pa.name} on {wo}: {score} ({pa.score_band}); CA {pa.corrective_action}")
	admin()
	# the good audit is reviewed and closed by operations
	frappe.set_user(OPS_HEAD)
	for name in frappe.get_all("Production Audit", filters={"audit_score": (">=", 70), "docstatus": 1}, pluck="name"):
		pa = frappe.get_doc("Production Audit", name)
		apply_workflow(pa, "Review")
		pa.reload()
		apply_workflow(pa, "Close Action")
	admin()


def step_quality_records():
	"""Non-conformance from incoming inspection + corrective actions."""
	if frappe.db.exists("Non Conformance", {"hml_source": "Incoming Inspection"}):
		return
	qi = frappe.db.get_value("Quality Inspection", {"hml_result": "Fail", "reference_type": "Purchase Receipt"}, ["name", "reference_name"], as_dict=True)
	nc = frappe.get_doc(
		{
			"doctype": "Non Conformance",
			"subject": "Hydraulic cylinders leaking at 250 bar - Hydro-Tech lot Oct-26",
			"procedure": "HML Manufacturing Quality Control",
			"status": "Open",
			"details": "<p>2 of 10 cylinders (PO3) leaked at the rod seal during incoming pressure test. Returned to supplier.</p>",
			"hml_company": COMPANY,
			"hml_source": "Incoming Inspection",
			"hml_item_code": "CMP-CYL-100",
			"hml_defect_reason": "Leak / pressure test failure",
			"hml_defect_qty": 2,
			"hml_cost_impact": 36000,
			"hml_quality_inspection": qi.name if qi else None,
			"hml_supplier": supplier_name("hydrotech"),
			"hml_rca_method": "5-Why",
			"hml_root_cause_category": "Material",
			"hml_root_cause": "Supplier changed rod-seal vendor in September without notification (PPAP not re-submitted).",
		}
	)
	nc.insert(ignore_permissions=True)
	ca = frappe.get_doc(
		{
			"doctype": "Corrective Action",
			"title": "Hydro-Tech: seal vendor change without PPAP",
			"company": COMPANY,
			"source": "Supplier Quality",
			"non_conformance": nc.name,
			"supplier": supplier_name("hydrotech"),
			"owner_user": user_email("vikram.rao"),
			"due_date": "2026-11-15",
			"status": "In Progress",
			"problem": "2/10 cylinders leaked at 250 bar; supplier changed seal source without notice.",
			"root_cause": "No change-notification clause in the supplier quality agreement.",
			"root_cause_category": "Material",
			"action_plan": "<ol><li>8D report from Hydro-Tech by 12 Nov</li><li>Add change-notification clause to SQA</li>"
			"<li>100 % pressure test of next 3 lots</li></ol>",
		}
	)
	ca.insert(ignore_permissions=True)
	nc.db_set("hml_corrective_action", ca.name)

	weld_nc = frappe.db.get_value("Non Conformance", {"hml_source": "In-Process Inspection"})
	if weld_nc:
		ca2 = frappe.get_doc(
			{
				"doctype": "Corrective Action",
				"title": "Weld porosity on HX-500 frames",
				"company": COMPANY,
				"source": "Non Conformance",
				"non_conformance": weld_nc,
				"work_order": frappe.db.get_value("Non Conformance", weld_nc, "hml_work_order"),
				"owner_user": user_email("suresh.patil"),
				"due_date": "2026-11-30",
				"status": "Open",
				"problem": "Porosity and undercut on the main fillet weld; frame needed 2 h rework.",
				"root_cause": "Electrodes not baked (E7018 is low-hydrogen); new welder unaware of WPS-07 storage rule.",
				"root_cause_category": "Man",
				"action_plan": "<p>Electrode oven at weld bay with log sheet; WPS-07 displayed at station.</p>",
				"training_required": 1,
				"training_topic": "WPS-07 low-hydrogen electrode handling and fillet weld technique",
				"training_employees": "Line A welders (both shifts)",
			}
		)
		ca2.insert(ignore_permissions=True)
		frappe.db.set_value("Non Conformance", weld_nc, {
			"hml_corrective_action": ca2.name, "hml_rca_method": "Fishbone (6M)", "hml_root_cause_category": "Man",
			"hml_root_cause": ca2.root_cause, "hml_cost_impact": 1620,
		})
	log("+ Non Conformances and Corrective Actions")


def step_capacity_conflict():
	"""Sales promises 2 presses by Friday 20 Nov while Line A is busy."""
	if frappe.db.exists("Sales Order", {"po_no": "APX/PO/2026/0533"}):
		return
	from erpnext.selling.doctype.quotation.quotation import _make_sales_order
	from horizon_erp.setup.seed.phase2 import quote_name

	frappe.set_user(SALES_EXEC)
	so = _make_sales_order(quote_name("Q9"), ignore_permissions=True)
	so.update({"transaction_date": "2026-11-18", "delivery_date": "2026-11-20", "po_no": "APX/PO/2026/0533", "po_date": "2026-11-18",
		"company_address": ADDRESS_MUMBAI, "set_warehouse": WH_FG, "payment_schedule": []})
	for row in so.items:
		row.delivery_date = "2026-11-20"
	so.insert()
	so.submit()
	admin()
	log(f"+ Sales Order {so.name}: 2 x HX-500 promised for Fri 20 Nov (risk flag {so.hml_delivery_risk})")
	wo = frappe.get_doc(
		{
			"doctype": "Work Order",
			"company": COMPANY,
			"production_item": "HX-500",
			"bom_no": frappe.db.get_value("Item", "HX-500", "default_bom"),
			"qty": 2,
			"use_multi_level_bom": 0,
			"sales_order": so.name,
			"sales_order_item": so.items[0].name,
			"wip_warehouse": WH_WIP,
			"fg_warehouse": WH_FG,
			"source_warehouse": WH_RM,
			"planned_start_date": "2026-11-19 06:00:00",
		}
	)
	wo.get_items_and_operations_from_bom()
	try:
		wo.insert(ignore_permissions=True)
	except frappe.ValidationError as e:
		frappe.clear_last_message()
		log(f"  capacity check blocked the WO as designed: {frappe.utils.strip_html(str(e))[:160]}...")
		wo.hml_capacity_decision = "Ship Partial"
		wo.hml_capacity_decision_note = (
			"Line A can finish 1 press by Thu 19 Nov for Friday dispatch; the second by 28 Nov. "
			"Amit agreed the split with Apex on 18 Nov; balance invoiced on delivery."
		)
		frappe.set_user(OPS_HEAD)
		wo.insert(ignore_permissions=True)
		admin()
	log(f"+ WO {wo.name}: needs {wo.hml_required_hours} h, free {wo.hml_line_free_hours} h -> {wo.hml_capacity_status} ({wo.hml_capacity_decision})")


def step_make_to_stock():
	"""A distributor order for conveyors raises a draft Work Order automatically."""
	if frappe.db.exists("Sales Order", {"po_no": "CMT/2026/311"}):
		return
	frappe.set_user(SALES_EXEC)
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer_name("capital"),
			"company": COMPANY,
			"transaction_date": "2026-11-18",
			"delivery_date": "2026-12-05",
			"po_no": "CMT/2026/311",
			"po_date": "2026-11-18",
			"company_address": ADDRESS_MUMBAI,
			"selling_price_list": "HML North Region Selling",
			"set_warehouse": WH_FG,
			"items": [{"item_code": "CX-200", "qty": 3, "delivery_date": "2026-12-05"}],
		}
	)
	so.insert()
	so.submit()
	admin()
	wo = frappe.db.get_value("Work Order", {"sales_order": so.name, "docstatus": 0}, ["name", "qty", "hml_production_line", "hml_capacity_status"], as_dict=True)
	log(f"+ Sales Order {so.name} (CX-200 x3, make-to-stock) -> draft WO {wo}")


STEPS = [
	("masters", step_masters),
	("hydraulic_oil", step_hydraulic_oil),
	("seal_kits", step_seal_kits),
	("boms", step_boms),
	("cx200_for_so1", step_cx200_for_so1),
	("hx500_for_so3", step_hx500_for_so3),
	("production_audits", step_production_audits),
	("quality_records", step_quality_records),
	("capacity_conflict", step_capacity_conflict),
	("make_to_stock", step_make_to_stock),
]
