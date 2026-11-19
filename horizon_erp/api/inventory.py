"""Inventory snapshot API for the Delhi DC (replaces the daily phone call).

POST /api/method/get_inventory_snapshot
	Authorization: token <api_key>:<api_secret>    (the API Client's user)
	body: {"warehouse": "Delhi DC", "filter_by_criticality": true}

* The bare path works through hooks.override_whitelisted_methods.
* "warehouse" accepts a warehouse name, its name without the " - HML" suffix,
  or a group (Delhi DC = every Delhi warehouse).
* Rate limit: API Client.rate_limit_per_hour (default 100) per client, counted
  in Redis per clock hour -> HTTP 429 with retry_after_seconds.
* Every call (success or failure) is written to API Request Log with
  parameters, status, duration and error.
* Errors: unknown warehouse -> 404 with the list of valid names; database or
  unexpected failure -> 503 with a timestamp and retry_after_seconds, never a
  stack trace.
"""

import json
import time

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from horizon_erp.constants import COMPANY

ENDPOINT = "get_inventory_snapshot"


class APIError(Exception):
	def __init__(self, status, message, **extra):
		super().__init__(message)
		self.status, self.message, self.extra = status, message, extra


@frappe.whitelist(methods=["POST"])
def get_inventory_snapshot(warehouse=None, filter_by_criticality=False):
	started = time.monotonic()
	params = {"warehouse": warehouse, "filter_by_criticality": filter_by_criticality}
	client = None
	try:
		client = _client_for(frappe.session.user)
		_check_rate_limit(client)
		data = _snapshot(warehouse, _truthy(filter_by_criticality), client)
		_log(client, params, 200, started)
		return data
	except APIError as e:
		frappe.local.response["http_status_code"] = e.status
		_log(client, params, e.status, started, e.message)
		return {"error": True, "status": e.status, "message": e.message, "timestamp": now_datetime().isoformat(), **e.extra}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="get_inventory_snapshot failed")
		frappe.local.response["http_status_code"] = 503
		_log(client, params, 503, started, f"{type(e).__name__}: {e}")
		return {
			"error": True,
			"status": 503,
			"message": "Inventory service temporarily unavailable. Retry after the given delay.",
			"timestamp": now_datetime().isoformat(),
			"retry_after_seconds": 60,
		}


def _truthy(v):
	return v in (True, 1, "1", "true", "True", "yes")


def _client_for(user):
	if user in ("Guest",):
		raise APIError(401, "Authentication required (token api_key:api_secret).")
	name = frappe.db.get_value("API Client", {"user": user}, ["name", "enabled", "rate_limit_per_hour", "allowed_warehouses"], as_dict=True)
	if not name:
		raise APIError(403, f"User {user} is not registered as an API Client.")
	if not name.enabled:
		raise APIError(403, f"API Client {name.name} is disabled.")
	return name


def _check_rate_limit(client):
	hour = now_datetime().strftime("%Y%m%d%H")
	key = frappe.cache.make_key(f"hml_api_rate::{client.name}::{hour}")  # site-prefixed
	count = frappe.cache.incrby(key, 1)
	if count == 1:
		frappe.cache.expire(key, 3600)
	limit = cint(client.rate_limit_per_hour) or 100
	if count > limit:
		now = now_datetime()
		retry = 3600 - (now.minute * 60 + now.second)
		raise APIError(429, f"Rate limit of {limit} requests per hour exceeded.", retry_after_seconds=retry, limit=limit)


def _resolve_warehouses(warehouse):
	if not warehouse:
		raise APIError(400, "Parameter 'warehouse' is required, e.g. 'Delhi DC'.")
	for candidate in (warehouse, f"{warehouse} - HML"):
		wh = frappe.db.get_value("Warehouse", {"name": candidate, "company": COMPANY}, ["name", "is_group", "lft", "rgt"], as_dict=True)
		if wh:
			if not wh.is_group:
				return wh.name, [wh.name]
			leaves = frappe.get_all(
				"Warehouse", filters={"lft": (">", wh.lft), "rgt": ("<", wh.rgt), "is_group": 0, "company": COMPANY}, pluck="name"
			)
			return wh.name, leaves
	valid = frappe.get_all("Warehouse", filters={"company": COMPANY}, pluck="name")
	raise APIError(404, f"Unknown warehouse '{warehouse}'.", valid_warehouses=[w.replace(" - HML", "") for w in valid])


def _snapshot(warehouse, filter_by_criticality, client):
	name, leaves = _resolve_warehouses(warehouse)
	if client.allowed_warehouses:
		allowed = {w.strip() for w in client.allowed_warehouses.splitlines() if w.strip()}
		if not ({name, name.replace(" - HML", "")} & allowed):
			raise APIError(403, f"Client {client.name} may not read {name}.")
	rows = frappe.db.sql(
		"""
		select b.item_code, i.item_name, i.hml_criticality criticality, i.stock_uom uom,
			sum(b.actual_qty) actual_qty, sum(b.reserved_qty) reserved_qty, sum(b.projected_qty) projected_qty,
			max(ir.warehouse_reorder_level) reorder_point, max(ir.warehouse_reorder_qty) reorder_qty
		from `tabBin` b join `tabItem` i on i.name = b.item_code
		left join `tabItem Reorder` ir on ir.parent = b.item_code and ir.warehouse = b.warehouse
		where b.warehouse in %s and (b.actual_qty != 0 or b.reserved_qty != 0)
		group by b.item_code order by i.item_group, b.item_code
		""",
		(tuple(leaves),),
		as_dict=True,
	)
	if filter_by_criticality:
		rows = [r for r in rows if (r.criticality or "").startswith(("A", "B"))]
	items, alerts = [], []
	for r in rows:
		available = flt(r.actual_qty) - flt(r.reserved_qty)
		item = {
			"item_code": r.item_code,
			"item_name": r.item_name,
			"uom": r.uom,
			"criticality": r.criticality,
			"available_qty": available,
			"reserved_qty": flt(r.reserved_qty),
			"reorder_point": flt(r.reorder_point),
			"reorder_qty": flt(r.reorder_qty),
		}
		items.append(item)
		if r.reorder_point and flt(r.projected_qty) < flt(r.reorder_point):
			alerts.append({"item_code": r.item_code, "available_qty": available, "reorder_point": flt(r.reorder_point),
				"suggested_order_qty": flt(r.reorder_qty)})
	return {
		"timestamp": now_datetime().isoformat(timespec="seconds"),
		"warehouse": name.replace(" - HML", ""),
		"warehouses_included": [w.replace(" - HML", "") for w in leaves],
		"items": items,
		"low_stock_alerts": alerts,
	}


def _log(client, params, status, started, error=None):
	try:
		frappe.get_doc(
			{
				"doctype": "API Request Log",
				"endpoint": ENDPOINT,
				"api_client": client.name if client else None,
				"user": frappe.session.user,
				"timestamp": now_datetime(),
				"status_code": status,
				"response_ms": round((time.monotonic() - started) * 1000, 1),
				"ip_address": getattr(frappe.local, "request_ip", None),
				"parameters": json.dumps(params, default=str),
				"error": error,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()  # keep the log even if the caller's transaction is rolled back
	except Exception:
		frappe.log_error(title="API Request Log write failed")
