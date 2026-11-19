"""Phase 3 - Buying, incoming quality, reorder and purchase planning.

Inspection checklists per material type, rejection reasons, legacy demand
history (Apr 2024 - Oct 2026, imported from the old ERP), reorder levels,
purchase orders through every approval tier (including the blacklisted
supplier exception and a rejected PO), receipts with Pass / Conditional Pass
/ Fail inspections, the automatic supplier return, auto reorder requests and
the Q4 purchase plan.
"""

import zlib

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, add_months, flt, get_datetime, getdate

from horizon_erp.constants import ADDRESS_MUMBAI, COMPANY, IG_COMPONENTS, IG_RAW, IG_SPARES, WH_RM
from horizon_erp.setup.seed.phase1 import ITEMS, supplier_name, user_email
from horizon_erp.setup.seed.utils import get_or_insert, log

BUYER = user_email("pooja.shah")
DEPT_HEAD = user_email("suresh.patil")
PROCUREMENT = user_email("vikram.rao")
FD = user_email("rajesh.menon")
QI_USER = user_email("ramesh.iyer")


def as_user(u):
	frappe.set_user(u)


def admin():
	frappe.set_user("Administrator")


# ----------------------------------------------------------- QC checklists

PARAMETERS = {
	# parameter: (numeric, min, max, value)
	"Plate Thickness (mm)": (1, 9.5, 10.5, None),
	"Mill Test Certificate Received": (0, None, None, "Yes"),
	"Surface Condition": (0, None, None, "No pitting / heavy rust"),
	"Pressure Test 250 bar - Leak": (0, None, None, "No Leak"),
	"Bore Diameter (mm)": (1, 99.95, 100.05, None),
	"Insulation Resistance (MOhm)": (1, 100, 100000, None),
	"No-load Current (A)": (1, 2.0, 6.5, None),
	"Nameplate Matches PO": (0, None, None, "Yes"),
	"Viscosity Ford Cup B4 (s)": (1, 60, 90, None),
	"Shade vs Approved Panel": (0, None, None, "Matches"),
	"Thread Go / No-Go": (0, None, None, "Pass"),
	"Hardness (HRC)": (1, 22, 32, None),
	"Visual Inspection": (0, None, None, "No damage"),
	"Critical Dimension Check": (0, None, None, "Within drawing tolerance"),
	"Batch Label and Expiry": (0, None, None, "Present and valid"),
}

TEMPLATES = {
	"HML Incoming - Steel": ["Plate Thickness (mm)", "Mill Test Certificate Received", "Surface Condition"],
	"HML Incoming - Hydraulics": ["Pressure Test 250 bar - Leak", "Bore Diameter (mm)", "Visual Inspection"],
	"HML Incoming - Electrical": ["Insulation Resistance (MOhm)", "No-load Current (A)", "Nameplate Matches PO"],
	"HML Incoming - Paint and Consumables": ["Viscosity Ford Cup B4 (s)", "Shade vs Approved Panel", "Batch Label and Expiry"],
	"HML Incoming - Fasteners and Bearings": ["Thread Go / No-Go", "Hardness (HRC)", "Visual Inspection"],
	"HML Incoming - Spares": ["Visual Inspection", "Critical Dimension Check"],
}

ITEM_TEMPLATE = {
	"RM-MS-PLATE-10": "HML Incoming - Steel",
	"RM-MS-CHANNEL-100": "HML Incoming - Steel",
	"RM-PAINT-EPOXY": "HML Incoming - Paint and Consumables",
	"RM-WELD-E7018": "HML Incoming - Paint and Consumables",
	"RM-HYD-OIL-68": "HML Incoming - Paint and Consumables",
	"RM-BELT-PVC-600": "HML Incoming - Spares",
	"RM-BOLT-M12": "HML Incoming - Fasteners and Bearings",
	"CMP-CYL-100": "HML Incoming - Hydraulics",
	"CMP-PUMP-GP20": "HML Incoming - Hydraulics",
	"CMP-MANIFOLD-HX": "HML Incoming - Hydraulics",
	"CMP-MOTOR-5HP": "HML Incoming - Electrical",
	"CMP-MOTOR-2HP": "HML Incoming - Electrical",
	"CMP-PLC-24": "HML Incoming - Electrical",
	"CMP-GEARBOX-30": "HML Incoming - Fasteners and Bearings",
	"CMP-BRG-6205": "HML Incoming - Fasteners and Bearings",
	"CMP-ROLLER-50": "HML Incoming - Fasteners and Bearings",
}

REJECTION_REASONS = [
	("Leak / pressure test failure", "Material", 1),
	("Dimension out of tolerance", "Dimensional", 1),
	("Wrong material grade", "Material", 1),
	("Surface defect / rust", "Material", 1),
	("Missing test certificate", "Documentation", 1),
	("Damaged in transit", "Transit Damage", 0),
	("Weld defect - porosity / undercut", "Process", 0),
	("Paint thickness out of spec", "Process", 0),
]


def step_quality_masters():
	for reason, category, supplier_related in REJECTION_REASONS:
		get_or_insert(
			"Quality Rejection Reason", reason, {"reason": reason, "category": category, "supplier_related": supplier_related}
		)
	for p in PARAMETERS:
		get_or_insert("Quality Inspection Parameter", p, {"parameter": p, "description": p})
	for name, params in TEMPLATES.items():
		if frappe.db.exists("Quality Inspection Template", name):
			continue
		rows = []
		for p in params:
			numeric, mn, mx, value = PARAMETERS[p]
			rows.append(
				{"specification": p, "numeric": numeric, "min_value": mn, "max_value": mx, "value": value}
			)
		get_or_insert(
			"Quality Inspection Template",
			name,
			{"quality_inspection_template_name": name, "item_quality_inspection_parameter": rows},
		)
	for item, template in ITEM_TEMPLATE.items():
		if frappe.db.get_value("Item", item, "quality_inspection_template") != template:
			frappe.db.set_value("Item", item, "quality_inspection_template", template)
	for code, spec in ITEMS.items():
		if spec[1] == IG_SPARES and not frappe.db.get_value("Item", code, "quality_inspection_template"):
			frappe.db.set_value("Item", code, "quality_inspection_template", "HML Incoming - Spares")


# ------------------------------------------------------------ demand history

BASE_DEMAND = {
	"RM-MS-PLATE-10": 1800, "RM-MS-CHANNEL-100": 1300, "RM-PAINT-EPOXY": 70, "RM-WELD-E7018": 60,
	"RM-HYD-OIL-68": 120, "RM-BELT-PVC-600": 40, "RM-BOLT-M12": 900,
	"CMP-CYL-100": 4, "CMP-PUMP-GP20": 4, "CMP-MOTOR-5HP": 6, "CMP-MOTOR-2HP": 9, "CMP-GEARBOX-30": 5,
	"CMP-PLC-24": 3, "CMP-BRG-6205": 220, "CMP-ROLLER-50": 120, "CMP-MANIFOLD-HX": 2,
	"SP-SEAL-KIT-HX": 30, "SP-FILTER-RET": 45, "SP-BELT-600-10M": 6, "SP-ROLLER-SET10": 14, "SP-HOSE-KIT": 12,
}
Q4_SPIKE = 1.8
HISTORY_START = "2024-04-01"
HISTORY_END = "2026-10-01"  # legacy ERP ran in parallel until November 2026 cut-over


def step_demand_history():
	if frappe.db.count("Item Demand History", {"source": "Legacy ERP"}) > 0:
		log("legacy demand history present")
		return
	month = getdate(HISTORY_START)
	rows = 0
	while month <= getdate(HISTORY_END):
		ym = month.strftime("%Y-%m")
		for item, base in BASE_DEMAND.items():
			seasonal = frappe.get_cached_value("Item", item, "hml_demand_pattern") == "Seasonal - Q4 Spike"
			factor = Q4_SPIKE if (seasonal and month.month in (1, 2, 3)) else 1.0
			growth = 1 + 0.01 * ((month.year - 2024) * 12 + month.month - 4) / 2  # ~6 % a year
			noise = 0.85 + (zlib.crc32(f"{item}{ym}".encode()) % 31) / 100  # 0.85 .. 1.15
			qty = round(base * factor * growth * noise, 0 if base > 20 else 1)
			frappe.get_doc(
				{"doctype": "Item Demand History", "item_code": item, "period": ym, "demand_qty": qty, "source": "Legacy ERP"}
			).insert(ignore_permissions=True)
			rows += 1
		month = add_months(month, 1)
	log(f"+ Item Demand History: {rows} legacy rows")


def step_reorder_levels():
	from horizon_erp.tasks.reorder import recalculate_reorder_levels

	for code, rop, qty in recalculate_reorder_levels(on_date="2026-11-01"):
		log(f"  reorder {code}: level {rop}, qty {qty}")


# ----------------------------------------------------------- purchase orders

POS = {
	"PO0": ("bharat", "2026-07-08", "2026-07-20", [("RM-MS-PLATE-10", 1500, 70), ("RM-MS-CHANNEL-100", 800, 66)],
		"Normal", "approve", {}),
	"PO0B": ("shree", "2026-07-10", "2026-07-14", [("RM-BOLT-M12", 2000, 11.5)], "Normal", "approve", {}),
	# key: supplier key, date, schedule, items[(code, qty, rate)], urgency, flow, extra
	"PO1": ("bharat", "2026-09-22", "2026-10-06", [("RM-MS-PLATE-10", 3000, 72), ("RM-MS-CHANNEL-100", 1500, 68)],
		"Normal", "approve", {}),
	"PO2": ("shree", "2026-10-01", "2026-10-03", [("RM-BOLT-M12", 3000, 12)], "Normal", "approve", {}),
	"PO3": ("hydrotech", "2026-10-03", "2026-10-28", [("CMP-CYL-100", 10, 18000), ("CMP-PUMP-GP20", 8, 12500)],
		"Urgent", "approve", {}),
	"PO4": ("delhielec", "2026-10-12", "2026-11-05", [("CMP-PLC-24", 10, 22000), ("CMP-MOTOR-5HP", 20, 14000)],
		"Normal", "approve", {}),
	"PO5": ("abcsupplies", "2026-10-15", "2026-11-04", [("CMP-MANIFOLD-HX", 6, 8600)], "Critical - Line Stoppage", "approve",
		{"hml_blacklist_override_reason": "Sole source for the HX-500 custom manifold block (drawing HX5-MF-07). "
			"No alternate qualified; 100 % incoming pressure test agreed with Quality as a condition."}),
	"PO6": ("rapid", "2026-10-20", "2026-10-27", [("RM-PAINT-EPOXY", 400, 460)], "Normal", "reject", {}),
	"PO7": ("precision", "2026-11-17", "2026-11-24", [("CMP-BRG-6205", 600, 180), ("CMP-GEARBOX-30", 6, 9800)],
		"Normal", "pending_dept", {}),
	"PO8": ("hydrotech", "2026-11-15", "2026-12-10", [("SP-SEAL-KIT-HX", 80, 2200), ("SP-HOSE-KIT", 40, 3100)],
		"Normal", "pending_proc", {}),
}


def po_name(key):
	return frappe.db.get_value("Purchase Order", {"title": f"{key} - HML seed", "docstatus": ("<", 2)})


def step_purchase_orders():
	for key, (sup, date, schedule, items, urgency, flow, extra) in POS.items():
		if po_name(key):
			continue
		as_user(BUYER)
		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"title": f"{key} - HML seed",
				"supplier": supplier_name(sup),
				"company": COMPANY,
				"transaction_date": date,
				"schedule_date": schedule,
				"billing_address": ADDRESS_MUMBAI,
				"shipping_address": ADDRESS_MUMBAI,
				"set_warehouse": WH_RM,
				"buying_price_list": "HML Standard Buying",
				"hml_urgency": urgency,
				"items": [
					{"item_code": c, "qty": q, "rate": r, "schedule_date": schedule, "warehouse": WH_RM} for c, q, r in items
				],
				**extra,
			}
		)
		po.insert()
		apply_workflow(po, "Submit for Approval")
		log(f"+ PO {po.name} [{key}] {po.supplier_name} Rs {po.base_grand_total:,.0f} tier {po.hml_approval_tier}")
		chain = {
			"1": [DEPT_HEAD],
			"2": [DEPT_HEAD, PROCUREMENT],
			"3": [DEPT_HEAD, PROCUREMENT, FD],
		}[po.hml_approval_tier[0]]
		if flow == "approve":
			for approver in chain:
				as_user(approver)
				po.reload()
				apply_workflow(po, "Approve")
		elif flow == "reject":
			as_user(DEPT_HEAD)
			po.reload()
			apply_workflow(po, "Approve")
			as_user(PROCUREMENT)
			po.reload()
			po.add_comment("Comment", "Rejected: Rs 460/L is 9.5 % above the last 3 purchases (Rs 420). Renegotiate or quote from a second supplier.")
			apply_workflow(po, "Reject")
		elif flow == "pending_proc":
			as_user(DEPT_HEAD)
			po.reload()
			apply_workflow(po, "Approve")
		admin()
		po.reload()
		log(f"  -> {po.name} {po.workflow_state} (docstatus {po.docstatus})")

	# realistic waiting times for the SLA dashboard (seed runs "now")
	for key, hours in (("PO7", 50), ("PO8", 30)):
		name = po_name(key)
		if name and frappe.db.get_value("Purchase Order", name, "docstatus") == 0:
			frappe.db.set_value(
				"Purchase Order",
				name,
				"hml_state_since",
				frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-hours),
				update_modified=False,
			)


# ----------------------------------------------------- receipts + inspection

RECEIPTS = [
	("PO0", "2026-07-18", "10:30:00", [("RM-MS-PLATE-10", "Pass", 0, None, None), ("RM-MS-CHANNEL-100", "Pass", 0, None, None)], 3.5),
	("PO0B", "2026-07-15", "12:00:00", [("RM-BOLT-M12", "Pass", 0, None, None)], 2.0),
	# po key, posting date, time, per item: (code, result, rejected_qty, reason, concession), inspection hours
	("PO1", "2026-10-05", "11:00:00", [("RM-MS-PLATE-10", "Pass", 0, None, None), ("RM-MS-CHANNEL-100", "Pass", 0, None, None)], 2.5),
	("PO2", "2026-10-03", "15:30:00", [("RM-BOLT-M12", "Pass", 0, None, None)], 1.0),
	("PO3", "2026-10-27", "10:15:00", [
		("CMP-CYL-100", "Fail", 2, "Leak / pressure test failure", None),
		("CMP-PUMP-GP20", "Conditional Pass", 0, None, "Paint scratches on 3 pump housings, functional test OK. Accepted by Priya Nair (Ops Head) - cosmetic only."),
	], 6.0),
	("PO4", "2026-11-06", "12:00:00", [("CMP-PLC-24", "Pass", 0, None, None), ("CMP-MOTOR-5HP", "Pass", 0, None, None)], 3.0),
	("PO5", "2026-11-05", "09:30:00", [("CMP-MANIFOLD-HX", "Pass", 0, None, None)], 1.5),
]


def step_receipts():
	for po_key, date, time, lines, hours in RECEIPTS:
		po = po_name(po_key)
		if not po or frappe.db.exists("Purchase Receipt Item", {"purchase_order": po, "docstatus": 1}):
			continue
		pr = make_purchase_receipt(po)
		pr.set_posting_time = 1
		pr.posting_date = date
		pr.posting_time = time
		pr.supplier_delivery_note = f"DC-{po_key}-{date[5:7]}{date[8:]}"
		pr.lr_no = f"LR{zlib.crc32(po.encode()) % 100000:05d}"
		pr.insert(ignore_permissions=True)
		received_at = get_datetime(f"{date} {time}")
		for row in pr.items:
			code, result, rej, reason, concession = next(l for l in lines if l[0] == row.item_code)
			qi = frappe.get_doc(
				{
					"doctype": "Quality Inspection",
					"inspection_type": "Incoming",
					"reference_type": "Purchase Receipt",
					"reference_name": pr.name,
					"child_row_reference": row.name,
					"item_code": row.item_code,
					"sample_size": min(flt(row.qty), 10),
					"report_date": date,
					"inspected_by": QI_USER,
					"quality_inspection_template": frappe.db.get_value("Item", row.item_code, "quality_inspection_template"),
					"hml_result": result,
					"hml_rejected_qty": rej or None,
					"hml_rejection_reason": reason,
					"hml_concession_note": concession,
					"hml_evidence_photo": "/assets/frappe/images/default-avatar.png" if result == "Fail" else None,
					"manual_inspection": 1,
				}
			)
			qi.get_item_specification_details()
			for reading in qi.readings:
				reading.status = "Accepted" if result != "Fail" else ("Rejected" if "Leak" in reading.specification else "Accepted")
				reading.reading_value = reading.value
				if reading.numeric:
					reading.reading_1 = str((flt(reading.min_value) + flt(reading.max_value)) / 2)
			qi.insert(ignore_permissions=True)
			qi.submit()
			qi.db_set(
				{
					"hml_received_at": received_at,
					"hml_inspection_hours": hours,
					"hml_sla_met": 1 if hours <= 4 else 0,
				},
				update_modified=False,
			)
		# QI submit writes itself onto the PR line (update_qc_reference)
		pr.reload()
		pr.save(ignore_permissions=True)  # applies accepted / rejected split
		pr.submit()
		rejected = [(r.item_code, r.rejected_qty) for r in pr.items if r.rejected_qty]
		log(f"+ GRN {pr.name} for {po_key} on {date}; rejected {rejected or 'none'}")


def step_auto_reorder():
	from horizon_erp.tasks.reorder import create_reorder_material_requests

	for mr in create_reorder_material_requests(on_date="2026-11-18"):
		log(f"+ auto Material Request {mr['material_request']} for {mr['supplier']}: {', '.join(mr['items'])}")


def step_purchase_plan():
	name = "QPP-2026-2027-Q4"
	if frappe.db.exists("Quarterly Purchase Plan", name):
		return
	plan = frappe.get_doc(
		{"doctype": "Quarterly Purchase Plan", "company": COMPANY, "fiscal_year": "2026-2027", "quarter": "Q4"}
	)
	plan.insert(ignore_permissions=True)
	n = plan.generate()
	log(f"+ {plan.name}: {n} items, planned value Rs {plan.total_planned_value:,.0f}")

	q3 = frappe.get_doc({"doctype": "Quarterly Purchase Plan", "company": COMPANY, "fiscal_year": "2026-2027", "quarter": "Q3"})
	if not frappe.db.exists("Quarterly Purchase Plan", "QPP-2026-2027-Q3"):
		q3.insert(ignore_permissions=True)
		q3.generate()
		q3.submit()
		q3.refresh_actuals()
		log(f"+ {q3.name}: planned Rs {q3.total_planned_value:,.0f}, actual Rs {q3.total_actual_value:,.0f}, variance {q3.variance_pct:.1f} %")


STEPS = [
	("quality_masters", step_quality_masters),
	("demand_history", step_demand_history),
	("reorder_levels", step_reorder_levels),
	("purchase_orders", step_purchase_orders),
	("receipts", step_receipts),
	("auto_reorder", step_auto_reorder),
	("purchase_plan", step_purchase_plan),
]
