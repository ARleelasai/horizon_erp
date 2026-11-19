import frappe, json, sys
def run(report, filters=None, user="Administrator"):
    from frappe.desk.query_report import run as qr
    frappe.set_user(user)
    r = qr(report, filters=filters or {}, ignore_prepared_report=True)
    print("columns:", [c.get("label") if isinstance(c, dict) else c for c in r["columns"]][:30])
    print("rows:", len(r["result"]))
    for row in r["result"][:int(frappe.flags.get("n") or 8)]:
        print(json.dumps(row, default=str)[:400])
    if r.get("report_summary"): print("summary:", r["report_summary"])
    if r.get("message"): print("message:", r["message"])
