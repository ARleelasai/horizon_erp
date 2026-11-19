"""HML API Usage - calls by endpoint and client, response-time trend, failures."""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	view = filters.view or "By Client"
	cond = {"timestamp": (">=", filters.from_date or "2026-11-01")}
	if view == "Failures":
		rows = frappe.get_all("API Request Log", filters={**cond, "status_code": (">=", 400)},
			fields=["timestamp", "endpoint", "api_client", "status_code", "error", "parameters", "response_ms"], order_by="timestamp desc")
		cols = [
			{"label": _("Time"), "fieldname": "timestamp", "fieldtype": "Datetime", "width": 160},
			{"label": _("Endpoint"), "fieldname": "endpoint", "fieldtype": "Data", "width": 170},
			{"label": _("Client"), "fieldname": "api_client", "fieldtype": "Link", "options": "API Client", "width": 140},
			{"label": _("HTTP"), "fieldname": "status_code", "fieldtype": "Int", "width": 60},
			{"label": _("Reason"), "fieldname": "error", "fieldtype": "Data", "width": 320},
			{"label": _("Parameters"), "fieldname": "parameters", "fieldtype": "Data", "width": 220},
		]
		return cols, rows
	if view == "Response Time Trend":
		rows = frappe.db.sql(
			"""select date_format(timestamp, '%%Y-%%m-%%d %%H:00') hour, count(*) calls, avg(response_ms) avg_ms, max(response_ms) max_ms,
				sum(status_code >= 400) failed
			from `tabAPI Request Log` where timestamp >= %s group by hour order by hour""",
			filters.from_date or "2026-11-01", as_dict=True)
		cols = [
			{"label": _("Hour"), "fieldname": "hour", "fieldtype": "Data", "width": 150},
			{"label": _("Calls"), "fieldname": "calls", "fieldtype": "Int", "width": 80},
			{"label": _("Avg ms"), "fieldname": "avg_ms", "fieldtype": "Float", "precision": 1, "width": 90},
			{"label": _("Max ms"), "fieldname": "max_ms", "fieldtype": "Float", "precision": 1, "width": 90},
			{"label": _("Failed"), "fieldname": "failed", "fieldtype": "Int", "width": 70},
		]
		chart = {"data": {"labels": [r.hour[5:] for r in rows], "datasets": [{"name": "Avg ms", "values": [round(r.avg_ms or 0, 1) for r in rows]}]}, "type": "line"}
		return cols, rows, None, chart
	rows = frappe.db.sql(
		"""select endpoint, ifnull(api_client, '(unknown)') api_client, count(*) calls, sum(status_code = 200) ok,
			sum(status_code = 429) rate_limited, sum(status_code >= 400 and status_code != 429) errors, avg(response_ms) avg_ms
		from `tabAPI Request Log` where timestamp >= %s group by endpoint, api_client order by calls desc""",
		filters.from_date or "2026-11-01", as_dict=True)
	cols = [
		{"label": _("Endpoint"), "fieldname": "endpoint", "fieldtype": "Data", "width": 180},
		{"label": _("Client"), "fieldname": "api_client", "fieldtype": "Data", "width": 160},
		{"label": _("Calls"), "fieldname": "calls", "fieldtype": "Int", "width": 80},
		{"label": _("OK"), "fieldname": "ok", "fieldtype": "Int", "width": 70},
		{"label": _("429 Rate-limited"), "fieldname": "rate_limited", "fieldtype": "Int", "width": 120},
		{"label": _("Other Errors"), "fieldname": "errors", "fieldtype": "Int", "width": 100},
		{"label": _("Avg ms"), "fieldname": "avg_ms", "fieldtype": "Float", "precision": 1, "width": 90},
	]
	return cols, rows
