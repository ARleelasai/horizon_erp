# Horizon ERP (`horizon_erp`)

ERPNext implementation for **Horizon Manufacturing Ltd** (assignment): a mid-size industrial equipment maker with an HQ plant in Mumbai and a distribution centre in Delhi. The app adds the validations, workflows, DocTypes, reports, scheduled jobs and API the brief asks for, on top of standard ERPNext / HRMS / India Compliance, plus an idempotent seed that builds the company and two months of realistic data.

| Item | Value |
|---|---|
| Frappe / ERPNext / HRMS / India Compliance | 15.54 / 15.50 / 15.49 / 15.14 |
| Site used | FSM.local (shared with another company, "Leelas", which is not affected) |
| Company | Horizon Manufacturing Ltd (HML) |
| Docs | Submitted separately: Configuration Design, Decision Memo, Business Process and Trade-offs, Inventory API |

## Layout

```
horizon_erp/
  constants.py            company, GSTINs, warehouses, roles (single source of truth)
  hooks.py                doc events, class override, scheduler, API alias, jinja
  setup/
    install.py            after_migrate: roles, custom fields, Location dimension, workflows, workspaces
    custom_fields.py      187 hml_* custom fields
    workflows.py          5 workflows + delivery notification
    workspaces.py         4 workspaces, 12 number cards, 3 charts
    seed/                 phase1..phase6 data (dry-run by default)
  overrides/              selling, buying, purchase_receipt (class), projects, hr, assets, dimensions
  manufacturing/          capacity check, quality gates, production audit gate, BOM revisions
  accounts/               bank auto-match + period lock, budget helpers
  strategy/               quality-vs-deadline scan, customer/supplier netting, migration rules
  tasks/                  scheduled jobs (reorder, approvals, reports, job logging + retry)
  api/                    inventory snapshot API, selling helper, Delhi retry client
  printing.py             jinja helpers for the print formats
  horizon_erp/doctype     20 DocTypes
  horizon_erp/report      38 script reports
  horizon_erp/print_format  HML Tax Invoice, HML Packing Slip 80mm
  data/                   CSV exports: customers, suppliers, items, BOMs, operations, employees, check-ins
  tests/smoke.py          14 business-rule checks (rolled back)
```

## Install on a v15 bench

```bash
cd ~/frappe-bench
bench get-app <repo-url> horizon_erp          # or copy the folder into apps/ and: ./env/bin/pip install -e apps/horizon_erp
bench --site <site> install-app horizon_erp   # needs erpnext, hrms, india_compliance
bench --site <site> migrate                    # registers the 11 scheduled jobs; install-app alone does not
bench restart                                  # or stop / start `bench start` so web, worker and scheduler load the app
```

`after_install` / `after_migrate` create roles, custom fields, the Location (Branch) accounting dimension, workflows, notification and workspaces. They are idempotent.

> Note: on a site with many apps, `bench --site <site> execute horizon_erp.setup.install.sync_app_files` reloads this app's DocTypes, reports, print formats and workspaces without a full `bench migrate`.

## Build the demo data

Each phase runs in one transaction and rolls back unless `commit=1`. Steps check before inserting, so a committed phase can be re-run safely.

```bash
for p in 1 2 3 4 5 6; do
  bench --site <site> execute horizon_erp.setup.seed.run --kwargs "{'phase': $p}"              # dry run
  bench --site <site> execute horizon_erp.setup.seed.run --kwargs "{'phase': $p, 'commit': 1}"  # persist
done
# one step only:
bench --site <site> execute horizon_erp.setup.seed.run --kwargs "{'phase': 2, 'steps': 'quotations', 'commit': 1}"
```

| Phase | Builds |
|---|---|
| 1 | Company, GSTINs, Location dimension, cost centers, accounts, warehouses, groups, price lists, 8 customers, 8 suppliers, 28 items, users and permissions, opening stock, recurring journals |
| 2 | Pricing rules, leads, opportunities, 9 quotations (approved, rejected, expired), 10 sales orders, pick lists, deliveries, auto invoices, Mumbai -> Delhi branch transfer |
| 3 | Inspection checklists, legacy demand history, reorder levels, POs through every approval tier incl. blacklist exception and rejection, receipts with Pass / Conditional / Fail, auto return, auto MR, purchase plans |
| 4 | Lines A / B, operations, 3-level BOMs with revisions and routings, work orders with job cards and inspections (incl. weld rework), production audits, NC / corrective actions, capacity conflict, make-to-stock WO |
| 5 | Holidays, shifts, leave setup, 22 employees, attendance and biometric check-ins, payroll (3 structures, tax slabs, IT declaration, October run), project with timesheets and milestone invoice, assets with depreciation, maintenance, disposal |
| 6 | Bank, receipts and payments, payment batches, statement import, auto-match, reconciliation lock, budgets + overage approval, RCM purchase, ABC Corp netting, quality-vs-deadline case, migration staging, obsolete stock scrap, API client, job runs |

The seed blocks outbound HTTP made by other apps' hooks in its own process and swaps a monkey-patched tax setup back to India Compliance's for company creation (see `setup/seed/guards.py`).

## Test

```bash
bench --site <site> execute horizon_erp.tests.smoke.run
```

Checks (all PASS on FSM.local, 19 Nov 2026, against the restarted bench on port 8000): typed prices refused, discount reason required, > 15 % discount needs approval, blacklist override and tier 3, PO tiers by amount, invoice before delivery refused, capacity conflict blocks the WO, audit hold blocks completion, GSTIN check digit, stock PI without PO refused, bank period lock, GSTIN auto-fix rules, CGST/SGST vs IGST by registration, credit limit.

API test: see the Inventory API document (04_Inventory_API).

## Logins (seeded, password `Horizon@2026`)

| User | Role in the story |
|---|---|
| rajesh.menon@horizonmfg.test | Finance Director (approves tier 3 POs, budget overages, big payment batches) |
| priya.nair@horizonmfg.test | Operations Head (audit escalations, capacity decisions) |
| amit.kapoor@horizonmfg.test | Sales Director |
| neha.joshi@horizonmfg.test | HR Manager |
| vikram.rao@horizonmfg.test | Procurement Manager |
| suresh.patil@horizonmfg.test | Department Head (Production) |
| sanjay.verma@horizonmfg.test / rohan.mehta@horizonmfg.test | Sales Manager / Sales Executive |
| pooja.shah@horizonmfg.test | Buyer |
| sunita.pawar@horizonmfg.test | Accounts User |
| anil.deshmukh@horizonmfg.test / kavita.singh@horizonmfg.test | Warehouse managers Mumbai / Delhi (location-restricted) |
| ramesh.iyer@horizonmfg.test | Quality Inspector |

## Operational notes

- Scheduled jobs need the scheduler and a worker (`bench start` or supervisor). Without an outgoing Email Account, notifications appear as bell notifications only.
- Workflows on Quotation and Purchase Order are site-wide; other companies get a plain "Submit" transition.
- Every rule checks `company == "Horizon Manufacturing Ltd"`.
- Labour rates live in Activity Cost, not Activity Type: agrica_fsm replaces Activity Type with a DocType that has no rate fields.
- `after_migrate` grants each HML role on an HML report read + report rights on the report's source doctype, because this site uses customised permissions.
