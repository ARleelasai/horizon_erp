"""Quarterly Purchase Plan.

Generate: for every HML purchased item,
	forecast_qty  = sum of monthly forecasts in the quarter (horizon_erp.planning)
	planned_qty   = forecast + safety stock - stock on hand - open PO/MR qty  (>= 0)
	order_by_date = quarter start - lead time (when the first order must go out)
Refresh Actuals (also after submit): ordered qty from submitted POs dated in
the quarter, variance = actual - planned, value variance % on the header.
"""

import math

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, add_months, flt, get_last_day, getdate

from horizon_erp.planning import forecast, monthly_demand, reorder_parameters, seasonal_index

QUARTER_START_MONTH = {"Q1": 0, "Q2": 3, "Q3": 6, "Q4": 9}  # months after fiscal year start


class QuarterlyPurchasePlan(Document):
	def validate(self):
		fy_start = getdate(frappe.db.get_value("Fiscal Year", self.fiscal_year, "year_start_date"))
		self.from_date = add_months(fy_start, QUARTER_START_MONTH[self.quarter])
		self.to_date = get_last_day(add_months(self.from_date, 2))
		self.title = f"{self.quarter} {self.fiscal_year} purchase plan"
		self.planning_basis = (
			"Forecast = 6-month de-seasonalised average x Q4 seasonal index (seasonal items); "
			"Planned = forecast + safety stock - on hand - open PO/MR; order-by = quarter start - lead time."
		)
		for row in self.items:
			row.planned_value = flt(row.planned_qty) * flt(row.rate)
		self.total_planned_value = sum(flt(r.planned_value) for r in self.items)

	@frappe.whitelist()
	def generate(self):
		self.validate()
		self.set("items", [])
		items = frappe.db.sql_list(
			"""select i.name from `tabItem` i join `tabItem Default` d on d.parent = i.name and d.company = %s
			where i.disabled = 0 and i.is_purchase_item = 1 and i.is_stock_item = 1 order by i.item_group, i.name""",
			self.company,
		)
		history = monthly_demand(items, add_months(self.from_date, -24), add_days(self.from_date, -1))
		months = [add_months(self.from_date, i) for i in range(3)]
		for code in items:
			index = seasonal_index(code, history)
			fc = sum(forecast(code, m, history, index) for m in months)
			params = reorder_parameters(code, self.from_date, history)
			warehouse = frappe.db.get_value("Item Default", {"parent": code, "company": self.company}, "default_warehouse")
			on_hand = flt(frappe.db.get_value("Bin", {"item_code": code, "warehouse": warehouse}, "actual_qty"))
			open_qty = flt(frappe.db.get_value("Bin", {"item_code": code, "warehouse": warehouse}, "ordered_qty")) + flt(
				frappe.db.get_value("Bin", {"item_code": code, "warehouse": warehouse}, "indented_qty")
			)
			planned = max(math.ceil(fc + params.safety_stock - on_hand - open_qty), 0)
			if not fc and not planned:
				continue
			supplier = frappe.db.get_value("Item Default", {"parent": code, "company": self.company}, "default_supplier")
			rate = flt(frappe.db.get_value("Item Price", {"item_code": code, "price_list": "HML Standard Buying"}, "price_list_rate"))
			self.append(
				"items",
				{
					"item_code": code,
					"supplier": supplier,
					"lead_time_days": params.lead_time,
					"forecast_qty": round(fc, 2),
					"safety_stock": params.safety_stock,
					"current_stock": on_hand,
					"open_order_qty": open_qty,
					"planned_qty": planned,
					"order_by_date": add_days(self.from_date, -params.lead_time),
					"rate": rate,
				},
			)
		self.validate()
		self.save()
		return len(self.items)

	@frappe.whitelist()
	def refresh_actuals(self):
		ordered = {
			r.item_code: r
			for r in frappe.db.sql(
				"""select poi.item_code, sum(poi.stock_qty) qty, sum(poi.base_net_amount) amount
				from `tabPurchase Order Item` poi join `tabPurchase Order` po on po.name = poi.parent
				where po.docstatus = 1 and po.company = %s and po.transaction_date between %s and %s
				group by poi.item_code""",
				(self.company, self.from_date, self.to_date),
				as_dict=True,
			)
		}
		actual_value = 0
		for row in self.items:
			o = ordered.get(row.item_code)
			row.actual_ordered_qty = flt(o.qty) if o else 0
			row.variance_qty = row.actual_ordered_qty - flt(row.planned_qty)
			actual_value += flt(o.amount) if o else 0
			row.db_update()
		self.total_actual_value = actual_value
		self.variance_pct = ((actual_value - flt(self.total_planned_value)) / flt(self.total_planned_value) * 100) if self.total_planned_value else 0
		self.db_update()
		return self.variance_pct
