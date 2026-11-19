frappe.query_reports["Audit Findings Dashboard"] = {
	filters: [
		{ fieldname: "view", label: __("View"), fieldtype: "Select", options: ["Recent Audits", "Low-Scoring Lines", "Pending Actions"], default: "Recent Audits", reqd: 1 },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -90) },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "audit_score") {
			const c = data.audit_score < 70 ? "#e24c4c" : data.audit_score < 85 ? "#f0ad4e" : "#28a745";
			return `<b style="color:${c}">${value}</b>`;
		}
		if (data && column.fieldname === "flag" && data.flag !== "OK") return `<span class="indicator-pill red">${value}</span>`;
		return value;
	},
};
