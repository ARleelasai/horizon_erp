"""Scheduled-job plumbing: logging, failure alerts, retry once.

Every Horizon job runs through run_logged(): the outcome goes to
Integration Log (Success / Findings / Failed). On failure the System
Managers are alerted and the log is marked "Retry Pending"; the hourly
retry_failed_jobs() re-runs each failed job exactly once (Retried OK /
Failed Again) - "retry once at next scheduled time".
"""

import json
import time
import traceback

import frappe
from frappe.utils import add_to_date, now_datetime

from horizon_erp.notify import notify


def run_logged(job, method, retry_of=None, **kwargs):
	started = now_datetime()
	t0 = time.monotonic()
	log = frappe.get_doc({"doctype": "Integration Log", "job": job, "method": method, "started_at": started, "retry_of": retry_of})
	frappe.db.savepoint("hml_job")
	try:
		result = frappe.get_attr(method)(**kwargs)
		findings = result if isinstance(result, (list, tuple)) else (result or {}).get("findings", []) if isinstance(result, dict) else []
		log.findings_count = len(findings)
		log.status = ("Retried OK" if retry_of else ("Findings" if findings else "Success"))
		log.details = json.dumps(result, default=str, indent=1)[:60000] if result else None
		log.summary = f"{len(findings)} finding(s)" if findings else "OK"
	except Exception as e:
		frappe.db.rollback(save_point="hml_job")  # undo only this job's partial work
		log.status = "Failed Again" if retry_of else "Retry Pending"
		log.error = traceback.format_exc()[-8000:]
		log.summary = f"{type(e).__name__}: {e}"[:500]
		admins = [u for u in frappe.get_all("Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent")
			if u not in ("Administrator", "Guest")]
		notify(admins, subject=f"Horizon job failed: {job}", message=f"<pre>{log.summary}</pre><p>Will retry once at the next hourly run.</p>"
			if not retry_of else f"<pre>{log.summary}</pre><p>Retry also failed. Investigate.</p>")
	log.duration_s = round(time.monotonic() - t0, 2)
	log.insert(ignore_permissions=True)
	frappe.db.commit()
	return log


def retry_failed_jobs():
	for row in frappe.get_all("Integration Log", filters={"status": "Retry Pending"}, fields=["name", "job", "method"]):
		frappe.db.set_value("Integration Log", row.name, "status", "Failed")
		run_logged(row.job, row.method, retry_of=row.name)


# --------------------------------------------------------------- job bodies


def hourly_inventory_job():
	"""Reorder requests + inventory accuracy check."""
	from horizon_erp.tasks.reorder import create_reorder_material_requests

	created = create_reorder_material_requests()
	mismatches = inventory_accuracy_check()
	return {"material_requests": created, "findings": [*created, *mismatches], "accuracy_mismatches": mismatches}


def inventory_accuracy_check():
	"""Calculated (balance in the stock ledger) vs recorded (Bin) qty per item /
	warehouse, plus physical-count variances posted by cycle counts in the
	last 24 hours. Stock reconciliation ledger rows carry qty_after_transaction,
	not actual_qty, so the latest balance is compared, not a sum."""
	from horizon_erp.constants import COMPANY

	rows = frappe.db.sql(
		"""select b.item_code, b.warehouse, b.actual_qty bin_qty,
			(select sle.qty_after_transaction from `tabStock Ledger Entry` sle
				where sle.item_code = b.item_code and sle.warehouse = b.warehouse and sle.is_cancelled = 0
				order by sle.posting_date desc, sle.posting_time desc, sle.creation desc limit 1) ledger_qty
		from `tabBin` b join `tabWarehouse` w on w.name = b.warehouse and w.company = %s""",
		COMPANY,
		as_dict=True,
	)
	out = []
	for r in rows:
		if abs((r.bin_qty or 0) - (r.ledger_qty or 0)) > 0.0001:
			out.append({"item_code": r.item_code, "warehouse": r.warehouse, "bin_qty": r.bin_qty, "ledger_qty": r.ledger_qty})
	# cycle-count variances recorded in the last 24 h (physical vs book)
	for r in frappe.db.sql(
		"""select sri.item_code, sri.warehouse, sri.current_qty, sri.qty, sr.name
		from `tabStock Reconciliation Item` sri join `tabStock Reconciliation` sr on sr.name = sri.parent
		where sr.company = %s and sr.docstatus = 1 and sr.purpose = 'Stock Reconciliation'
			and sr.modified >= %s and abs(sri.qty - sri.current_qty) > 0""",
		(COMPANY, add_to_date(now_datetime(), hours=-24)),
		as_dict=True,
	):
		out.append({"item_code": r.item_code, "warehouse": r.warehouse, "book_qty": r.current_qty, "counted_qty": r.qty, "voucher": r.name})
	return out


def hourly():
	run_logged("Hourly inventory: reorder + accuracy", "horizon_erp.tasks.jobs.hourly_inventory_job")
	retry_failed_jobs()


def daily_summary():
	run_logged("Daily Finance Director summary", "horizon_erp.tasks.reports.send_daily_summary")


def monthly_budget():
	run_logged("Monthly budget performance mail", "horizon_erp.tasks.reports.send_monthly_budget_reports")


def selftest_flaky():
	"""Demo job for the retry path: fails the first time, succeeds on retry
	(the earlier failure is read from Integration Log, so it works across
	worker processes)."""
	failed_before = frappe.db.exists(
		"Integration Log", {"method": "horizon_erp.tasks.jobs.selftest_flaky", "status": ("in", ["Retry Pending", "Failed"])}
	)
	if not failed_before:
		raise ConnectionError("Simulated database timeout (self-test)")
	return {"findings": [], "note": "self-test retry succeeded"}
