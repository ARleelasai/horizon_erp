"""Small helpers shared by the seed phases."""

import frappe
from frappe.utils import flt

GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin(state_code, pan, entity="1"):
	"""Build a GSTIN with a valid check digit: <state><PAN><entity>Z<check>."""
	body = f"{state_code}{pan}{entity}Z"
	factor, total = 1, 0
	for ch in body:
		d = factor * GSTIN_CHARS.find(ch)
		total += d // 36 + d % 36
		factor = 2 if factor == 1 else 1
	return body + GSTIN_CHARS[(36 - total % 36) % 36]


def log(*a):
	print("  ", *a, flush=True)


def get_or_insert(doctype, filters, values=None, set_name=None, submit=False):
	"""Return existing doc matching filters, else insert one from values."""
	name = frappe.db.exists(doctype, filters)
	if name:
		return frappe.get_doc(doctype, name)
	values = values or (filters if isinstance(filters, dict) else {})
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.insert(set_name=set_name, ignore_permissions=True)
	if submit:
		doc.submit()
	log(f"+ {doctype}: {doc.name}")
	return doc


def ensure_value(doctype, name, values):
	"""Set fields on an existing doc only when they differ (no-op otherwise)."""
	doc = frappe.get_doc(doctype, name)
	changed = False
	for k, v in values.items():
		cur = doc.get(k)
		if isinstance(v, (int, float)) and not isinstance(v, bool):
			if flt(cur) != flt(v):
				doc.set(k, v)
				changed = True
		elif cur != v:
			doc.set(k, v)
			changed = True
	if changed:
		doc.save(ignore_permissions=True)
		log(f"~ {doctype}: {name}")
	return doc


def set_posting(doc, date, time="10:00:00"):
	doc.set_posting_time = 1
	doc.posting_date = date
	if hasattr(doc, "posting_time"):
		doc.posting_time = time
