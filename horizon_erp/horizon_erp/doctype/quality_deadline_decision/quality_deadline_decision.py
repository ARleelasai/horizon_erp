"""Quality Deadline Decision - the conflict is made explicit, costed and signed.

Raised automatically (horizon_erp.strategy.conflicts) or by hand. Every
function records its position; the decision needs the acknowledgement of the
roles it affects before it can be submitted:
	Ship Partial + Rework Balance        -> Sales, Operations, Quality
	Delay Delivery                       -> Sales (customer agreed), Operations
	Invoice Now, Ship Later (bill & hold)-> Sales, Finance (customer request in writing)
	Ship with Customer-Approved Concession -> Sales, Quality (customer agreed)
	Overtime Rework, Ship on Time        -> Operations, Finance (cost)
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

REQUIRED = {
	"Ship Partial + Rework Balance": ("sales_ack", "operations_ack", "quality_ack"),
	"Delay Delivery": ("sales_ack", "operations_ack"),
	"Invoice Now, Ship Later": ("sales_ack", "finance_ack"),
	"Ship with Customer-Approved Concession": ("sales_ack", "quality_ack"),
	"Overtime Rework, Ship on Time": ("operations_ack", "finance_ack"),
}
ROLE_FIELD = {
	"HML Sales Director": "sales_ack",
	"HML Operations Head": "operations_ack",
	"Quality Manager": "quality_ack",
	"HML Finance Director": "finance_ack",
}


class QualityDeadlineDecision(Document):
	def validate(self):
		so = frappe.db.get_value("Sales Order", self.sales_order, ["delivery_date", "customer_name"], as_dict=True)
		self.delivery_date = so.delivery_date
		self.title = f"{so.customer_name}: {self.item_code} due {frappe.format(so.delivery_date, 'Date')}"
		pending = frappe.db.sql(
			"select sum(stock_qty - delivered_qty) from `tabSales Order Item` where parent = %s and item_code = %s",
			(self.sales_order, self.item_code),
		)[0][0]
		self.ordered_qty = flt(pending)
		self.cost_of_delay = flt(self.cost_of_delay_per_day) * flt(self.delay_days)

	def before_submit(self):
		if not self.decision:
			frappe.throw(_("Record the decision before submitting."))
		missing = [f for f in REQUIRED[self.decision] if not self.get(f)]
		if missing:
			frappe.throw(_("Still needs sign-off from: {0}").format(", ".join(self.meta.get_label(f) for f in missing)))
		if self.decision in ("Delay Delivery", "Ship with Customer-Approved Concession", "Invoice Now, Ship Later") and not self.customer_agreed:
			frappe.throw(_("This option needs the customer's written agreement (tick Customer Agreed and attach it)."))
		if self.decision == "Delay Delivery" and self.new_delivery_date:
			frappe.db.sql(
				"update `tabSales Order Item` set delivery_date = %s where parent = %s and item_code = %s",
				(self.new_delivery_date, self.sales_order, self.item_code),
			)

	@frappe.whitelist()
	def acknowledge(self):
		"""Each function signs off in its own session; stored on the doc."""
		roles = frappe.get_roles()
		fields = [f for role, f in ROLE_FIELD.items() if role in roles]
		if not fields:
			frappe.throw(_("Your role does not sign off quality / deadline decisions."))
		for f in fields:
			self.db_set(f, frappe.session.user)
		return fields
