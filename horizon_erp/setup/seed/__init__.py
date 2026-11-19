"""Seed runner for Horizon Manufacturing Ltd test data.

Usage (from v15-bench):

    bench --site FSM.local execute horizon_erp.setup.seed.run --kwargs "{'phase': 1}"
    bench --site FSM.local execute horizon_erp.setup.seed.run --kwargs "{'phase': 1, 'commit': 1}"

Without commit=1 it is a dry run: the whole phase runs in one transaction,
inner commits are suppressed, and everything is rolled back at the end.

Every step is idempotent (lookup before insert), so a committed phase can be
re-run safely; existing records are left alone.

While the seed runs, outbound HTTP from other apps' hooks (DataHub, Neo4j
microservice, GST API) is short-circuited in this process only. The site's
settings are not changed.
"""

import importlib
import time
import traceback

import frappe

PHASES = {
	1: "horizon_erp.setup.seed.phase1",
	2: "horizon_erp.setup.seed.phase2",
	3: "horizon_erp.setup.seed.phase3",
	4: "horizon_erp.setup.seed.phase4",
	5: "horizon_erp.setup.seed.phase5",
	6: "horizon_erp.setup.seed.phase6",
}


def run(phase, commit=0, steps=None):
	"""Run one seed phase. `steps` optionally limits to a comma-separated list."""
	phase = int(phase)
	commit = int(commit)
	module = importlib.import_module(PHASES[phase])
	selected = [s.strip() for s in steps.split(",")] if steps else None

	frappe.set_user("Administrator")
	frappe.flags.mute_emails = True
	frappe.flags.hml_seed = True

	from horizon_erp.setup.seed.guards import external_calls_blocked

	real_commit = frappe.db.commit
	frappe.db.commit = lambda *a, **k: None
	ok = False
	t0 = time.time()
	try:
		with external_calls_blocked():
			for name, fn in module.STEPS:
				if selected and name not in selected:
					continue
				print(f"== phase {phase} / {name}", flush=True)
				fn()
		ok = True
	except Exception:
		traceback.print_exc()
	finally:
		frappe.db.commit = real_commit
		if ok and commit:
			frappe.db.commit()
			print(f"\nCOMMITTED phase {phase} in {time.time() - t0:.1f}s")
		else:
			frappe.db.rollback()
			print("\nROLLED BACK (dry run)" if ok else "\nFAILED - rolled back")
		frappe.clear_cache()
		frappe.flags.hml_seed = False
	if not ok:
		raise SystemExit(1)
