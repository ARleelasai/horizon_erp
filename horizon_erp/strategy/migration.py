"""Legacy data clean-up rules and the preventive checks that stop the same
problems coming back.

Clean-up (classify_staging_rows):
	Invalid GSTIN
		auto-fix  : whitespace / lower case / O-vs-0, I-vs-1 typos when the
		            corrected string passes the check digit AND its state code
		            matches the customer's state
		review    : anything else (wrong state, wrong PAN, failed checksum)
	Negative stock
		auto-fix  : |qty| x valuation <= Rs 5,000 and not serial/batch -> post
		            to stock adjustment at go-live (absorb as variance)
		review    : larger values, serial or batch items (traceability)
	Purchase invoice without PO
		auto-fix  : non-stock services / utilities below Rs 50,000 (no PO
		            needed by policy) -> import as is
		review    : stock items, or above Rs 50,000 (possible maverick buy)

Preventive (doc events, Horizon only):
	* GSTIN: India Compliance already enforces format, check digit, the
	  address state vs GSTIN state code (address.validate_state), and derives
	  the party PAN from the GSTIN - so no Horizon code is needed there.
	* Purchase Invoice: stock items need a PO or Purchase Receipt.
	* Stock: negative stock stays disabled (Stock Settings) - documented.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import flt

from horizon_erp.constants import COMPANY

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
STATE_CODES = {"Maharashtra": "27", "Delhi": "07", "Karnataka": "29", "Gujarat": "24", "Tamil Nadu": "33", "Telangana": "36"}
STOCK_ABSORB_LIMIT = 5000
PI_NO_PO_LIMIT = 50000


def checksum_ok(gstin):
	chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
	factor, total = 1, 0
	for ch in gstin[:-1]:
		d = factor * chars.find(ch)
		total += d // 36 + d % 36
		factor = 2 if factor == 1 else 1
	return gstin[-1] == chars[(36 - total % 36) % 36]


def try_fix_gstin(raw, state):
	g = re.sub(r"\s+", "", (raw or "")).upper()
	candidates = [g]
	if len(g) == 15:
		# common OCR / typing swaps in the PAN digits block (positions 8-11) and the letter block
		swapped = list(g)
		for i in range(7, 11):
			swapped[i] = {"O": "0", "I": "1", "S": "5"}.get(swapped[i], swapped[i])
		for i in list(range(2, 7)) + [11]:
			swapped[i] = {"0": "O", "1": "I", "5": "S"}.get(swapped[i], swapped[i])
		candidates.append("".join(swapped))
	for c in candidates:
		if GSTIN_RE.match(c) and checksum_ok(c) and STATE_CODES.get(state) == c[:2]:
			return c
	return None


def classify_staging_rows():
	out = {"Auto-fixed": 0, "Needs Review": 0}
	for row in frappe.get_all("Migration Staging Row", filters={"status": "Pending"}, fields=["*"]):
		payload = json.loads(row.payload or "{}")
		status, rule, corrected = "Needs Review", None, None
		if row.issue in ("Invalid GSTIN", "GSTIN State Mismatch"):
			corrected = try_fix_gstin(row.original_value, payload.get("state"))
			if corrected:
				status, rule = "Auto-fixed", "GSTIN normalised (spacing/case/O-0 swap); check digit and state code verified"
			else:
				rule = "GSTIN fails check digit or state code - confirm with customer / GST portal"
		elif row.issue == "Negative Stock":
			value = abs(flt(row.qty)) * flt(payload.get("valuation_rate"))
			if value <= STOCK_ABSORB_LIMIT and not payload.get("serial_or_batch"):
				status, rule, corrected = "Auto-fixed", f"Absorb at go-live: write {row.qty:g} to zero via stock adjustment (Rs {value:,.0f} <= {STOCK_ABSORB_LIMIT:,})", "0"
			else:
				rule = f"Value Rs {value:,.0f} or traceable item - physical count required before import"
		elif row.issue == "Purchase Invoice Without PO":
			if not payload.get("has_stock_items") and flt(row.amount) <= PI_NO_PO_LIMIT:
				status, rule = "Auto-fixed", "Service / utility bill under Rs 50,000 - PO not required by policy"
			else:
				rule = "Stock purchase or > Rs 50,000 without PO - Finance to confirm approval trail"
		frappe.db.set_value("Migration Staging Row", row.name, {"status": status, "rule": rule, "corrected_value": corrected})
		out[status] += 1
	return out


# ----------------------------------------------------------- preventive checks


def validate_purchase_invoice_po(doc, method=None):
	if doc.company != COMPANY or doc.is_return or doc.get("is_internal_supplier") or doc.update_stock:
		return
	for row in doc.items:
		if frappe.get_cached_value("Item", row.item_code, "is_stock_item") and not (row.purchase_order or row.purchase_receipt):
			frappe.throw(
				_("Row {0}: {1} is a stock item. Bill it against a Purchase Order / Receipt (unordered stock purchases are not allowed).").format(
					row.idx, row.item_code
				),
				title=_("PO required"),
			)
