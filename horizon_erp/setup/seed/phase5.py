"""Phase 5 - Projects, assets, HR and payroll for Horizon Manufacturing Ltd.

HR: holidays, shifts (Morning 06-14, Afternoon 14-22, General), HML leave
types and policy (CL 12, SL 8, EL 21 with max 10 carried forward), leave
block dates, 22 employees across three pay categories, October attendance
(manual) and November biometric check-ins with auto attendance and late
flags, leave applications incl. a blocked conflicting leave.

Payroll: salary components, three salary structures (salaried CTC %, hourly
wage earners from attendance hours + overtime, contractual fee), grades,
new and old regime tax slabs, an IT declaration, October payroll run.

Projects: a custom test-rig project from a Sales Order, tasks with budgeted
hours and milestones, daily timesheets (one with overtime), material issued
to the project, milestone invoice raised automatically.

Assets: categories, existing plant (opening depreciation), new purchases
capitalised through Purchase Invoices, monthly depreciation posted,
maintenance jobs and the sale of a retired compressor.
"""

import zlib

import frappe
from frappe.desk.form.assign_to import add as assign_to
from frappe.utils import add_days, flt, get_datetime, getdate

from horizon_erp.constants import (
	ABBR,
	ADDRESS_MUMBAI,
	BRANCH_DELHI,
	BRANCH_MUMBAI,
	COMPANY,
	WH_RM,
	acc,
	cc,
)
from horizon_erp.setup.seed.phase1 import customer_name, user_email
from horizon_erp.setup.seed.utils import ensure_value, get_or_insert, log

HOLIDAY_LIST = "HML 2026-27"
FY_START, FY_END = "2026-04-01", "2027-03-31"


def admin():
	frappe.set_user("Administrator")


def dept(name):
	return f"{name} - {ABBR}"


# ----------------------------------------------------------------- accounts


def step_accounts():
	for name, parent, account_type in [
		("Insurance Premium Payable", "Current Liabilities", ""),
		("Employee Loans", "Loans and Advances (Assets)", ""),
		("Vehicles", "Fixed Assets", "Fixed Asset"),
	]:
		get_or_insert(
			"Account",
			acc(name),
			{"account_name": name, "parent_account": acc(parent), "company": COMPANY, "is_group": 0, "account_type": account_type},
		)
	ensure_value(
		"Company",
		COMPANY,
		{
			"default_payroll_payable_account": acc("Payroll Payable"),
			"accumulated_depreciation_account": acc("Accumulated Depreciations"),
			"depreciation_expense_account": acc("Depreciation"),
			"disposal_account": acc("Gain/Loss on Asset Disposal"),
			"depreciation_cost_center": cc("Mfg - Equipment"),
		},
	)


# --------------------------------------------------------- holidays & shifts

HOLIDAYS = [
	("2026-04-14", "Ambedkar Jayanti"), ("2026-05-01", "Maharashtra Day / Labour Day"), ("2026-08-15", "Independence Day"),
	("2026-09-14", "Ganesh Chaturthi"), ("2026-10-02", "Gandhi Jayanti"), ("2026-10-20", "Dussehra"),
	("2026-11-09", "Diwali (Lakshmi Puja)"), ("2026-11-10", "Diwali (Balipratipada)"), ("2026-12-25", "Christmas"),
	("2026-12-28", "Plant shutdown - annual maintenance"), ("2026-12-29", "Plant shutdown - annual maintenance"),
	("2026-12-30", "Plant shutdown - annual maintenance"), ("2026-12-31", "Plant shutdown - annual maintenance"),
	("2027-01-26", "Republic Day"), ("2027-03-04", "Holi"),
]


def step_holidays_and_shifts():
	if not frappe.db.exists("Holiday List", HOLIDAY_LIST):
		hl = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": HOLIDAY_LIST,
				"from_date": FY_START,
				"to_date": FY_END,
				"weekly_off": "Sunday",
				"holidays": [{"holiday_date": d, "description": t} for d, t in HOLIDAYS],
			}
		)
		hl.get_weekly_off_dates()
		hl.insert(ignore_permissions=True)
		log(f"+ Holiday List {HOLIDAY_LIST}: {len(hl.holidays)} days")
	ensure_value("Company", COMPANY, {"default_holiday_list": HOLIDAY_LIST})

	for name, start, end in [("HML Morning Shift", "06:00:00", "14:00:00"), ("HML Afternoon Shift", "14:00:00", "22:00:00"),
			("HML General Shift", "09:30:00", "18:00:00")]:
		get_or_insert(
			"Shift Type",
			name,
			{
				"start_time": start,
				"end_time": end,
				"holiday_list": HOLIDAY_LIST,
				"enable_auto_attendance": 1,
				"determine_check_in_and_check_out": "Alternating entries as IN and OUT during the same shift",
				"working_hours_calculation_based_on": "First Check-in and Last Check-out",
				"begin_check_in_before_shift_start_time": 60,
				"allow_check_out_after_shift_end_time": 180,
				"enable_late_entry_marking": 1,
				"late_entry_grace_period": 5,
				"enable_early_exit_marking": 1,
				"early_exit_grace_period": 5,
				"working_hours_threshold_for_half_day": 4,
				"working_hours_threshold_for_absent": 2,
				"process_attendance_after": "2026-11-01",
				"last_sync_of_checkin": "2026-11-18 23:59:00",
			},
			set_name=name,
		)


# ------------------------------------------------------------------- leaves


def step_leave_setup():
	for name, days, carry, max_cf, expiry, extra in [
		("HML Casual Leave", 12, 0, 0, 0, {"max_continuous_days_allowed": 3}),
		("HML Sick Leave", 8, 0, 0, 0, {}),
		# no "max leaves allowed" cap on EL: HRMS would trim the carried-forward 10 to fit 21
		("HML Earned Leave", 0, 1, 10, 365, {"applicable_after": 0}),
	]:
		get_or_insert(
			"Leave Type",
			name,
			{
				"leave_type_name": name,
				"max_leaves_allowed": days,
				"is_carry_forward": carry,
				"maximum_carry_forwarded_leaves": max_cf,
				"expire_carry_forwarded_leaves_after_days": expiry,
				"include_holiday": 0,
				**extra,
			},
		)
	get_or_insert(
		"Leave Policy",
		{"title": "HML Standard Leave Policy"},
		{
			"title": "HML Standard Leave Policy",
			"leave_policy_details": [
				{"leave_type": "HML Casual Leave", "annual_allocation": 12},
				{"leave_type": "HML Sick Leave", "annual_allocation": 8},
				{"leave_type": "HML Earned Leave", "annual_allocation": 21},
			],
		},
		submit=True,
	)
	for name, start, end in [("HML FY 2025-26", "2025-04-01", "2026-03-31"), ("HML FY 2026-27", FY_START, FY_END)]:
		if not frappe.db.exists("Leave Period", {"company": COMPANY, "from_date": start}):
			frappe.get_doc({"doctype": "Leave Period", "from_date": start, "to_date": end, "company": COMPANY, "is_active": 1}).insert(
				ignore_permissions=True
			)
	if not frappe.db.exists("Leave Block List", "HML Shutdown and Stock Count"):
		frappe.get_doc(
			{
				"doctype": "Leave Block List",
				"leave_block_list_name": "HML Shutdown and Stock Count",
				"company": COMPANY,
				"applies_to_all_departments": 1,
				"year": "2026-2027",
				"leave_block_list_dates": [
					{"block_date": "2026-12-26", "reason": "Pre-shutdown dispatch day"},
					{"block_date": "2027-03-30", "reason": "Annual physical stock count"},
					{"block_date": "2027-03-31", "reason": "Year-end close and stock count"},
				],
				"leave_block_list_allowed": [{"allow_user": user_email("neha.joshi")}],
			}
		).insert(ignore_permissions=True)
		log("+ Leave Block List HML Shutdown and Stock Count")


# ---------------------------------------------------------------- employees

# key: (first, last, gender, dob, doj, department, designation, category, pay, grade, branch, shift, user key, manager key)
EMPLOYEES = {
	"rajesh": ("Rajesh", "Menon", "Male", "1974-03-11", "2012-06-01", "Accounts", "Finance Director", "Salaried Staff", 4200000, "G3 Director", BRANCH_MUMBAI, "HML General Shift", "rajesh.menon", None),
	"priya": ("Priya", "Nair", "Female", "1979-08-23", "2014-01-15", "Operations", "Operations Head", "Salaried Staff", 3600000, "G3 Director", BRANCH_MUMBAI, "HML General Shift", "priya.nair", None),
	"amit": ("Amit", "Kapoor", "Male", "1980-11-02", "2015-04-01", "Sales", "Sales Director", "Salaried Staff", 3400000, "G3 Director", BRANCH_MUMBAI, "HML General Shift", "amit.kapoor", None),
	"neha": ("Neha", "Joshi", "Female", "1986-02-17", "2016-07-11", "Human Resources", "HR Manager", "Salaried Staff", 1800000, "G2 Manager", BRANCH_MUMBAI, "HML General Shift", "neha.joshi", None),
	"vikram": ("Vikram", "Rao", "Male", "1984-05-30", "2017-03-20", "Purchase", "Procurement Manager", "Salaried Staff", 1500000, "G2 Manager", BRANCH_MUMBAI, "HML General Shift", "vikram.rao", "rajesh"),
	"suresh": ("Suresh", "Patil", "Male", "1982-09-09", "2013-10-01", "Production", "Production Manager", "Salaried Staff", 1400000, "G2 Manager", BRANCH_MUMBAI, "HML General Shift", "suresh.patil", "priya"),
	"anil": ("Anil", "Deshmukh", "Male", "1988-12-12", "2018-02-05", "Operations", "Stores Manager", "Salaried Staff", 720000, "G2 Manager", BRANCH_MUMBAI, "HML General Shift", "anil.deshmukh", "priya"),
	"kavita": ("Kavita", "Singh", "Female", "1990-04-04", "2020-08-17", "Dispatch", "Warehouse Manager", "Salaried Staff", 660000, "G2 Manager", BRANCH_DELHI, "HML General Shift", "kavita.singh", "priya"),
	"ramesh": ("Ramesh", "Iyer", "Male", "1991-07-21", "2019-05-02", "Quality Management", "QC Inspector", "Salaried Staff", 540000, "G1 Executive", BRANCH_MUMBAI, "HML General Shift", "ramesh.iyer", "priya"),
	"sanjay": ("Sanjay", "Verma", "Male", "1985-01-28", "2016-09-12", "Sales", "Sales Manager", "Salaried Staff", 1200000, "G2 Manager", BRANCH_MUMBAI, "HML General Shift", "sanjay.verma", "amit"),
	"rohan": ("Rohan", "Mehta", "Male", "1996-10-15", "2022-06-20", "Sales", "Sales Executive", "Salaried Staff", 480000, "G1 Executive", BRANCH_MUMBAI, "HML General Shift", "rohan.mehta", "sanjay"),
	"pooja": ("Pooja", "Shah", "Female", "1997-03-03", "2023-01-09", "Purchase", "Purchase Executive", "Salaried Staff", 360000, "G1 Executive", BRANCH_MUMBAI, "HML General Shift", "pooja.shah", "vikram"),
	"sunita": ("Sunita", "Pawar", "Female", "1995-06-18", "2021-11-01", "Accounts", "Accounts Assistant", "Salaried Staff", 228000, "G1 Executive", BRANCH_MUMBAI, "HML General Shift", None, "rajesh"),
	"mahesh": ("Mahesh", "Gaikwad", "Male", "1989-02-02", "2015-03-16", "Production", "Welder", "Wage Earner", 160, None, BRANCH_MUMBAI, "HML Morning Shift", None, "suresh"),
	"iqbal": ("Iqbal", "Shaikh", "Male", "1990-08-08", "2016-12-05", "Production", "Welder", "Wage Earner", 155, None, BRANCH_MUMBAI, "HML Afternoon Shift", None, "suresh"),
	"santosh": ("Santosh", "Jadhav", "Male", "1987-05-25", "2014-07-07", "Production", "Fitter", "Wage Earner", 140, None, BRANCH_MUMBAI, "HML Morning Shift", None, "suresh"),
	"ravi": ("Ravi", "Yadav", "Male", "1993-11-30", "2019-04-22", "Production", "Fitter", "Wage Earner", 135, None, BRANCH_MUMBAI, "HML Afternoon Shift", None, "suresh"),
	"dinesh": ("Dinesh", "Kamble", "Male", "1992-01-14", "2018-10-01", "Production", "Painter", "Wage Earner", 125, None, BRANCH_MUMBAI, "HML Morning Shift", None, "suresh"),
	"arjun": ("Arjun", "Thakur", "Male", "1998-09-19", "2023-06-12", "Production", "Machine Operator", "Wage Earner", 130, None, BRANCH_MUMBAI, "HML Afternoon Shift", None, "suresh"),
	"farhan": ("Farhan", "Qureshi", "Male", "1991-12-01", "2025-07-01", "Research & Development", "CAD Designer", "Contractual", 65000, None, BRANCH_MUMBAI, "HML General Shift", None, "priya"),
	"meera": ("Meera", "Kulkarni", "Female", "1989-04-27", "2025-10-01", "Production", "Safety Officer", "Contractual", 55000, None, BRANCH_MUMBAI, "HML General Shift", None, "priya"),
	"tushar": ("Tushar", "Bhosale", "Male", "1990-02-11", "2026-04-01", "Management", "IT Consultant", "Contractual", 80000, None, BRANCH_MUMBAI, "HML General Shift", None, "rajesh"),
}

DEPT_COST_CENTER = {
	"Accounts": "Admin", "Human Resources": "Admin", "Management": "Admin", "Operations": "Mfg - Equipment",
	"Production": "Mfg - Equipment", "Quality Management": "Mfg - Equipment", "Purchase": "Admin", "Sales": "Sales",
	"Dispatch": "Sales", "Research & Development": "R&D",
}


def emp(key):
	first, last = EMPLOYEES[key][0], EMPLOYEES[key][1]
	return frappe.db.get_value("Employee", {"first_name": first, "last_name": last, "company": COMPANY})


def step_employees():
	for grade in ("G1 Executive", "G2 Manager", "G3 Director"):
		get_or_insert("Employee Grade", grade, {"__newname": grade}, set_name=grade)
	for key, row in EMPLOYEES.items():
		designation = row[6]
		if not frappe.db.exists("Designation", designation):
			frappe.get_doc({"doctype": "Designation", "designation_name": designation}).insert(ignore_permissions=True)
	for key, (first, last, gender, dob, doj, department, designation, category, pay, grade, branch, shift, user, _mgr) in EMPLOYEES.items():
		if emp(key):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Employee",
				"naming_series": "HR-EMP-",
				"first_name": first,
				"last_name": last,
				"gender": gender,
				"date_of_birth": dob,
				"date_of_joining": doj,
				"company": COMPANY,
				"department": dept(department),
				"designation": designation,
				"employment_type": "Contract" if category == "Contractual" else "Full-time",
				"grade": grade,
				"branch": branch,
				"default_shift": shift,
				"holiday_list": HOLIDAY_LIST,
				"hml_employee_category": category,
				"hml_hourly_rate": pay if category == "Wage Earner" else None,
				"ctc": pay if category == "Salaried Staff" else (pay * 12 if category == "Contractual" else pay * 8 * 26 * 12),
				"user_id": user_email(user) if user else None,
				"payroll_cost_center": cc(DEPT_COST_CENTER[department]),
				"status": "Active",
				"pan_number": f"ABCP{chr(65 + zlib.crc32(key.encode()) % 26)}{1000 + zlib.crc32(key.encode()) % 9000}K",
				"provident_fund_account": None if category == "Contractual" else f"MH/BAN/0047312/{zlib.crc32(key.encode()) % 100000:05d}",
				"cell_number": f"+91 98{zlib.crc32(key.encode()) % 100000000:08d}",
				"prefered_email": f"{first.lower()}.{last.lower()}@horizonmfg.test",
			}
		)
		doc.insert(ignore_permissions=True)
		log(f"+ Employee {doc.name} {first} {last} ({category})")
	# managers / approvers (second pass, now that everyone exists)
	for key, row in EMPLOYEES.items():
		mgr = row[13]
		if not mgr:
			continue
		approver = user_email(EMPLOYEES[mgr][12]) if EMPLOYEES[mgr][12] else None
		frappe.db.set_value("Employee", emp(key), {"reports_to": emp(mgr), "leave_approver": approver, "expense_approver": approver})
	for d in ("Production", "Sales", "Purchase", "Accounts", "Operations"):
		head = {"Production": "suresh", "Sales": "amit", "Purchase": "vikram", "Accounts": "rajesh", "Operations": "priya"}[d]
		department = frappe.get_doc("Department", dept(d))
		if not department.leave_approvers:
			department.append("leave_approvers", {"approver": user_email(EMPLOYEES[head][12])})
			department.save(ignore_permissions=True)


def step_shift_assignments():
	for key, row in EMPLOYEES.items():
		if row[7] != "Wage Earner":
			continue
		e = emp(key)
		if frappe.db.exists("Shift Assignment", {"employee": e, "docstatus": 1}):
			continue
		sa = frappe.get_doc(
			{"doctype": "Shift Assignment", "employee": e, "company": COMPANY, "shift_type": row[11], "start_date": "2026-10-01", "status": "Active"}
		)
		sa.insert(ignore_permissions=True)
		sa.submit()
	log("+ Shift assignments for shop-floor workers")


def step_leave_allocation():
	staff = [k for k, r in EMPLOYEES.items() if r[7] != "Contractual"]
	# previous year earned leave for three long-serving people, partly used -> carry forward
	history = {"suresh": ("2025-12-15", "2025-12-20"), "mahesh": ("2026-01-12", "2026-01-17"), "santosh": ("2026-02-09", "2026-02-14")}
	for key, (h_from, h_to) in history.items():
		e = emp(key)
		if not frappe.db.exists("Leave Allocation", {"employee": e, "leave_type": "HML Earned Leave", "from_date": "2025-04-01"}):
			la = frappe.get_doc(
				{"doctype": "Leave Allocation", "employee": e, "leave_type": "HML Earned Leave", "from_date": "2025-04-01",
					"to_date": "2026-03-31", "new_leaves_allocated": 21}
			)
			la.insert(ignore_permissions=True)
			la.submit()
			lap = frappe.get_doc(
				{"doctype": "Leave Application", "employee": e, "leave_type": "HML Earned Leave", "from_date": h_from,
					"to_date": h_to, "status": "Approved", "leave_approver": user_email("priya.nair") if key == "suresh" else user_email("suresh.patil"),
					"description": "Annual leave", "posting_date": add_days(h_from, -14)}
			)
			lap.insert(ignore_permissions=True)
			lap.submit()
	period = frappe.db.get_value("Leave Period", {"company": COMPANY, "from_date": FY_START})
	policy = frappe.db.get_value("Leave Policy", {"title": "HML Standard Leave Policy", "docstatus": 1})
	for key in staff:
		e = emp(key)
		if frappe.db.exists("Leave Policy Assignment", {"employee": e, "docstatus": 1, "effective_from": FY_START}):
			continue
		lpa = frappe.get_doc(
			{
				"doctype": "Leave Policy Assignment",
				"employee": e,
				"company": COMPANY,
				"leave_policy": policy,
				"assignment_based_on": "Leave Period",
				"leave_period": period,
				"effective_from": FY_START,
				"effective_to": FY_END,
				"carry_forward": 1 if key in ("suresh", "mahesh", "santosh") else 0,
			}
		)
		lpa.insert(ignore_permissions=True)
		lpa.submit()
	log(f"+ Leave policy assigned to {len(staff)} employees (3 with carry forward)")
	_apply_carry_forward(history)


def _apply_carry_forward(employees):
	"""Re-allocate EL with carry forward (capped at 10 by the leave type) for
	allocations booked before the leave type cap was removed."""
	for key in employees:
		e = emp(key)
		name = frappe.db.get_value(
			"Leave Allocation", {"employee": e, "leave_type": "HML Earned Leave", "from_date": FY_START, "docstatus": 1},
			["name", "unused_leaves"], as_dict=True,
		)
		if not name or flt(name.unused_leaves) > 0:
			continue
		old = frappe.get_doc("Leave Allocation", name.name)
		old.flags.ignore_links = True
		old.cancel()
		new = frappe.copy_doc(old)
		new.amended_from = None
		new.carry_forward = 1
		new.leave_policy_assignment = old.leave_policy_assignment
		new.insert(ignore_permissions=True)
		new.submit()
		log(f"  {key}: Earned Leave carried forward {new.unused_leaves}, total {new.total_leaves_allocated}")


# --------------------------------------------------------------- attendance


def _workdays(start, end):
	holidays = set(str(d) for d in frappe.get_all("Holiday", filters={"parent": HOLIDAY_LIST}, pluck="holiday_date"))
	d = getdate(start)
	while d <= getdate(end):
		if str(d) not in holidays:
			yield d
		d = add_days(d, 1)


def step_october_attendance():
	"""Manual / bulk attendance for October (payroll month)."""
	if frappe.db.exists("Attendance", {"company": COMPANY, "attendance_date": "2026-10-05"}):
		return
	count = 0
	for key, row in EMPLOYEES.items():
		e = emp(key)
		category = row[7]
		for d in _workdays("2026-10-01", "2026-10-31"):
			seed = zlib.crc32(f"{key}{d}".encode()) % 100
			status = "Absent" if seed < 3 else "Present"
			hours = 8.0
			if category == "Wage Earner" and status == "Present":
				hours = 10.0 if seed > 85 else (8.5 if seed > 70 else 8.0)
			att = frappe.get_doc(
				{
					"doctype": "Attendance",
					"employee": e,
					"company": COMPANY,
					"attendance_date": d,
					"status": status,
					"shift": row[11],
					"working_hours": hours if status == "Present" else 0,
				}
			)
			att.insert(ignore_permissions=True)
			att.submit()
			count += 1
	log(f"+ October attendance: {count} records")


def step_november_checkins():
	"""Biometric punches for shop-floor workers 2-18 Nov, then auto attendance."""
	workers = [k for k, r in EMPLOYEES.items() if r[7] == "Wage Earner"]
	if frappe.db.exists("Employee Checkin", {"employee": emp(workers[0])}):
		return
	n = 0
	for key in workers:
		e = emp(key)
		start = "06:00:00" if EMPLOYEES[key][11] == "HML Morning Shift" else "14:00:00"
		for d in _workdays("2026-11-02", "2026-11-18"):
			seed = zlib.crc32(f"{key}{d}ck".encode()) % 100
			if seed < 4:
				continue  # absent, no punch
			late = 9 if seed > 88 else (3 if seed > 60 else -12)  # >5 min = late beyond grace
			t_in = frappe.utils.add_to_date(get_datetime(f"{d} {start}"), minutes=late)
			extra = 120 if seed in range(40, 48) else 0  # overtime days
			early = -15 if seed in range(20, 23) else 0
			t_out = frappe.utils.add_to_date(get_datetime(f"{d} {start}"), hours=8, minutes=extra + early + 2)
			for log_type, t in (("IN", t_in), ("OUT", t_out)):
				frappe.get_doc(
					{"doctype": "Employee Checkin", "employee": e, "log_type": log_type, "time": t, "device_id": "BIO-MUM-GATE-01",
						"shift": EMPLOYEES[key][11]}
				).insert(ignore_permissions=True)
				n += 1
	for shift in ("HML Morning Shift", "HML Afternoon Shift"):
		st = frappe.get_doc("Shift Type", shift)
		st.process_auto_attendance()
	late = frappe.db.count("Attendance", {"company": COMPANY, "late_entry": 1, "attendance_date": (">=", "2026-11-01")})
	log(f"+ {n} biometric check-ins; auto attendance marked; {late} late entries flagged")


def step_leave_applications():
	if frappe.db.exists("Leave Application", {"employee": emp("ravi"), "from_date": "2026-11-23"}):
		return
	approver = user_email("suresh.patil")
	frappe.set_user(approver)
	for key, lt, f, t, reason in [
		("ravi", "HML Casual Leave", "2026-11-23", "2026-11-24", "Family function"),
		("dinesh", "HML Casual Leave", "2026-11-24", "2026-11-25", "Personal work"),
	]:
		lap = frappe.get_doc(
			{"doctype": "Leave Application", "employee": emp(key), "leave_type": lt, "from_date": f, "to_date": t,
				"status": "Approved", "leave_approver": approver, "description": reason, "posting_date": "2026-11-16"}
		)
		lap.insert(ignore_permissions=True)
		lap.submit()
		log(f"+ Leave approved {lap.name} {key} {f}..{t}")
	# a third person from the same 8-person department on 24 Nov breaks the 25 % rule
	lap = frappe.get_doc(
		{"doctype": "Leave Application", "employee": emp("arjun"), "leave_type": "HML Casual Leave", "from_date": "2026-11-24",
			"to_date": "2026-11-24", "status": "Open", "leave_approver": approver, "description": "Bank work", "posting_date": "2026-11-17"}
	)
	lap.insert(ignore_permissions=True)
	lap.status = "Approved"
	try:
		lap.save(ignore_permissions=True)
		log("  !! conflicting leave was approved (rule not applied)")
	except frappe.ValidationError as e:
		frappe.clear_last_message()
		lap.reload()
		lap.add_comment("Comment", f"Approval refused by system: {frappe.utils.strip_html(str(e))}")
		log(f"  conflicting leave {lap.name} stays Open: {frappe.utils.strip_html(str(e))[:90]}...")
	admin()


# ------------------------------------------------------------------ payroll

COMPONENTS = [
	# name, abbr, type, account, depends_on_payment_days, extra
	("Basic", "B", "Earning", "Salary", 1, {}),
	("Dearness Allowance", "DA", "Earning", "Salary", 1, {}),
	("House Rent Allowance", "HRA", "Earning", "Salary", 1, {}),
	("Medical Allowance", "MA", "Earning", "Salary", 1, {}),
	("Conveyance Allowance", "CONV", "Earning", "Salary", 1, {}),
	("Special Allowance", "SPA", "Earning", "Salary", 1, {}),
	("Basic Wages", "BW", "Earning", "Manufacturing Wages", 0, {}),
	("Overtime", "OT", "Earning", "Manufacturing Wages", 0, {}),
	("Production Incentive", "PINC", "Earning", "Manufacturing Wages", 0, {}),
	("Contract Fee", "CF", "Earning", "Contract Labour Charges", 1, {}),
	("Provident Fund", "PF", "Deduction", "PF Payable", 0, {}),
	("ESI Employee", "ESI", "Deduction", "ESI Payable", 0, {}),
	("Professional Tax", "PT", "Deduction", "Professional Tax Payable", 0, {}),
	("Income Tax", "IT", "Deduction", "TDS on Salary Payable", 0, {"variable_based_on_taxable_salary": 1, "is_income_tax_component": 1}),
	("TDS on Contract Fee", "TDSC", "Deduction", "TDS on Salary Payable", 0, {}),
	("Insurance Premium", "INS", "Deduction", "Insurance Premium Payable", 0, {}),
	("Loan Recovery", "LR", "Deduction", "Employee Loans", 0, {}),
	("PF Employer", "PFE", "Deduction", None, 0, {"statistical_component": 1}),
	("ESI Employer", "ESIE", "Deduction", None, 0, {"statistical_component": 1}),
]

STAFF_GROSS = "(B + DA + HRA + MA + CONV + SPA)"
PT_MUMBAI = 'branch == "HQ Mumbai"'

STRUCTURES = {
	"HML Salaried Staff": {
		"earnings": [
			("Basic", "base * 0.40", None),
			("Dearness Allowance", "base * 0.10", None),
			# every earning is a % of base (monthly CTC) so each one prorates by payment days
			("House Rent Allowance", "base * 0.20", None),
			("Medical Allowance", "1250", None),
			("Conveyance Allowance", "1600", None),
			("Special Allowance", "base * 0.30 - 2850", None),
		],
		"deductions": [
			# PF wage ceiling Rs 15,000 (HRMS formulas have no min())
			("Provident Fund", "((B + DA) if (B + DA) < 15000 else 15000) * 0.12", None),
			("PF Employer", "((B + DA) if (B + DA) < 15000 else 15000) * 0.12", None),
			("ESI Employee", f"{STAFF_GROSS} * 0.0075", f"{STAFF_GROSS} <= 21000"),
			("ESI Employer", f"{STAFF_GROSS} * 0.0325", f"{STAFF_GROSS} <= 21000"),
			("Professional Tax", "200", f"{PT_MUMBAI} and {STAFF_GROSS} > 10000"),
			("Income Tax", None, None),
		],
	},
	"HML Wage Earner": {
		"earnings": [
			("Basic Wages", "base * hml_hours_worked", None),
			("Overtime", "base * 2 * hml_overtime_hours", "hml_overtime_hours > 0"),
		],
		"deductions": [
			("Provident Fund", "(BW if BW < 15000 else 15000) * 0.12", None),
			("PF Employer", "(BW if BW < 15000 else 15000) * 0.12", None),
			("ESI Employee", "(BW + OT) * 0.0075", "(BW + OT) <= 21000"),
			("ESI Employer", "(BW + OT) * 0.0325", "(BW + OT) <= 21000"),
			("Professional Tax", "200", f"{PT_MUMBAI} and (BW + OT) > 10000"),
		],
	},
	"HML Contractual": {
		"earnings": [("Contract Fee", "base", None)],
		"deductions": [("TDS on Contract Fee", "CF * 0.10", None)],
	},
}


def step_payroll_masters():
	for name, abbr, ctype, account, dpd, extra in COMPONENTS:
		if frappe.db.exists("Salary Component", name):
			doc = frappe.get_doc("Salary Component", name)
		else:
			doc = frappe.new_doc("Salary Component")
			doc.salary_component = name
			doc.salary_component_abbr = abbr
			doc.type = ctype
		doc.depends_on_payment_days = dpd
		doc.update(extra)
		if account and not [a for a in doc.accounts if a.company == COMPANY]:
			doc.append("accounts", {"company": COMPANY, "account": acc(account)})
		doc.save(ignore_permissions=True)

	for code, (name, parent) in {"80C": ("Section 80C", None), "80D": ("Section 80D", None)}.items():
		get_or_insert("Employee Tax Exemption Category", name, {"name": name, "max_amount": 150000 if code == "80C" else 50000}, set_name=name)
	for sub, cat, mx in [("Life Insurance Premium", "Section 80C", 150000), ("Public Provident Fund", "Section 80C", 150000),
			("Mediclaim - Self and Family", "Section 80D", 25000)]:
		get_or_insert("Employee Tax Exemption Sub Category", sub, {"exemption_category": cat, "max_amount": mx, "is_active": 1}, set_name=sub)

	if not frappe.db.exists("Payroll Period", "HML FY 2026-27"):
		frappe.get_doc(
			{"doctype": "Payroll Period", "__newname": "HML FY 2026-27", "company": COMPANY, "start_date": FY_START, "end_date": FY_END}
		).insert(ignore_permissions=True, set_name="HML FY 2026-27")

	cess = [{"description": "Health and Education Cess", "percent": 4, "min_taxable_income": 0, "max_taxable_income": 0}]
	for name, exemption, relief, allow_exempt, slabs in [
		("HML New Regime FY 2026-27", 75000, 1200000, 0,
			[(0, 400000, 0), (400000, 800000, 5), (800000, 1200000, 10), (1200000, 1600000, 15), (1600000, 2000000, 20), (2000000, 2400000, 25), (2400000, 0, 30)]),
		("HML Old Regime FY 2026-27", 50000, 500000, 1,
			[(0, 250000, 0), (250000, 500000, 5), (500000, 1000000, 20), (1000000, 0, 30)]),
	]:
		if frappe.db.exists("Income Tax Slab", {"name": name}):
			continue
		slab = frappe.get_doc(
			{
				"doctype": "Income Tax Slab",
				"__newname": name,
				"effective_from": FY_START,
				"company": COMPANY,
				"currency": "INR",
				"standard_tax_exemption_amount": exemption,
				"tax_relief_limit": relief,
				"allow_tax_exemption": allow_exempt,
				"slabs": [{"from_amount": f, "to_amount": t, "percent_deduction": p} for f, t, p in slabs],
				"other_taxes_and_charges": cess,
			}
		)
		slab.insert(ignore_permissions=True, set_name=name)
		slab.submit()

	for name, parts in STRUCTURES.items():
		if frappe.db.exists("Salary Structure", name):
			continue
		ss = frappe.get_doc(
			{
				"doctype": "Salary Structure",
				"__newname": name,
				"company": COMPANY,
				"payroll_frequency": "Monthly",
				"currency": "INR",
				"is_active": "Yes",
				"earnings": [_component_row(c, f, cond) for c, f, cond in parts["earnings"]],
				"deductions": [_component_row(c, f, cond) for c, f, cond in parts["deductions"]],
			}
		)
		ss.insert(ignore_permissions=True, set_name=name)
		ss.submit()
		log(f"+ Salary Structure {name}")
	for grade, structure, base in [("G1 Executive", "HML Salaried Staff", 30000), ("G2 Manager", "HML Salaried Staff", 90000),
			("G3 Director", "HML Salaried Staff", 300000)]:
		frappe.db.set_value("Employee Grade", grade, {"default_salary_structure": structure, "default_base_pay": base})


def _component_row(component, formula, condition):
	row = {"salary_component": component, "abbr": frappe.db.get_value("Salary Component", component, "salary_component_abbr")}
	if formula:
		row.update({"amount_based_on_formula": 1, "formula": formula})
	if condition:
		row["condition"] = condition
	return row


def step_salary_assignments():
	for key, row in EMPLOYEES.items():
		e = emp(key)
		if frappe.db.exists("Salary Structure Assignment", {"employee": e, "docstatus": 1}):
			continue
		category, pay = row[7], row[8]
		structure, base = {
			"Salaried Staff": ("HML Salaried Staff", round(pay / 12, 0)),
			"Wage Earner": ("HML Wage Earner", pay),
			"Contractual": ("HML Contractual", pay),
		}[category]
		slab = "HML Old Regime FY 2026-27" if key == "rajesh" else "HML New Regime FY 2026-27"
		ssa = frappe.get_doc(
			{
				"doctype": "Salary Structure Assignment",
				"employee": e,
				"salary_structure": structure,
				"company": COMPANY,
				"from_date": max(FY_START, str(row[4])),
				"base": base,
				"currency": "INR",
				"income_tax_slab": slab,
				"payroll_payable_account": acc("Payroll Payable"),
				"payroll_cost_centers": (
					[{"cost_center": cc("Mfg - Equipment"), "percentage": 60}, {"cost_center": cc("Mfg - Spares"), "percentage": 25},
						{"cost_center": cc("Mfg - Components"), "percentage": 15}]
					if category == "Wage Earner"
					else [{"cost_center": cc(DEPT_COST_CENTER[row[5]]), "percentage": 100}]
				),
			}
		)
		ssa.insert(ignore_permissions=True)
		ssa.submit()
	log("+ Salary Structure Assignments")

	e = emp("rajesh")
	if not frappe.db.exists("Employee Tax Exemption Declaration", {"employee": e, "docstatus": 1}):
		d = frappe.get_doc(
			{
				"doctype": "Employee Tax Exemption Declaration",
				"employee": e,
				"company": COMPANY,
				"payroll_period": "HML FY 2026-27",
				"currency": "INR",
				"declarations": [
					{"exemption_sub_category": "Life Insurance Premium", "exemption_category": "Section 80C", "amount": 90000},
					{"exemption_sub_category": "Public Provident Fund", "exemption_category": "Section 80C", "amount": 60000},
					{"exemption_sub_category": "Mediclaim - Self and Family", "exemption_category": "Section 80D", "amount": 25000},
				],
			}
		)
		d.insert(ignore_permissions=True)
		d.submit()
		log(f"+ IT declaration {d.name} for Rajesh (old regime): 80C 1.5 L, 80D 25 K")


def step_payroll_run():
	"""October payroll, one run per location (HQ Mumbai, DC Delhi)."""
	if not frappe.db.exists("Additional Salary", {"company": COMPANY, "payroll_date": "2026-10-31"}):
		for key, comp, amount in [("mahesh", "Production Incentive", 2500), ("iqbal", "Production Incentive", 2000),
				("santosh", "Production Incentive", 1800), ("dinesh", "Production Incentive", 1500),
				("rajesh", "Insurance Premium", 2500), ("priya", "Insurance Premium", 2500), ("santosh", "Loan Recovery", 3000)]:
			ad = frappe.get_doc(
				{"doctype": "Additional Salary", "employee": emp(key), "company": COMPANY, "salary_component": comp, "amount": amount,
					"payroll_date": "2026-10-31", "overwrite_salary_structure_amount": 1, "currency": "INR"}
			)
			ad.insert(ignore_permissions=True)
			ad.submit()
	for branch in (BRANCH_MUMBAI, BRANCH_DELHI):
		if frappe.db.exists("Payroll Entry", {"company": COMPANY, "start_date": "2026-10-01", "branch": branch, "docstatus": 1}):
			continue
		pe = frappe.get_doc(
			{
				"doctype": "Payroll Entry",
				"company": COMPANY,
				"branch": branch,
				"posting_date": "2026-10-31",
				"payroll_frequency": "Monthly",
				"start_date": "2026-10-01",
				"end_date": "2026-10-31",
				"currency": "INR",
				"exchange_rate": 1,
				"cost_center": cc("Admin"),
				"payroll_payable_account": acc("Payroll Payable"),
				"payment_account": acc("HDFC Bank - Current Account"),
			}
		)
		pe.insert(ignore_permissions=True)
		pe.fill_employee_details()
		pe.save(ignore_permissions=True)
		pe.submit()  # creates draft salary slips
		pe.reload()
		pe.submit_salary_slips()
		pe.reload()
		slips = frappe.get_all(
			"Salary Slip", filters={"payroll_entry": pe.name},
			fields=["employee_name", "gross_pay", "net_pay", "hml_hours_worked", "hml_overtime_hours", "docstatus"],
		)
		log(f"+ Payroll Entry {pe.name} ({branch}): {len(slips)} slips, gross Rs {sum(s.gross_pay for s in slips):,.0f}, net Rs {sum(s.net_pay for s in slips):,.0f}")
		for s in slips:
			if s.hml_hours_worked:
				log(f"    {s.employee_name}: {s.hml_hours_worked} h + {s.hml_overtime_hours} OT h -> gross {s.gross_pay:,.0f}")


# ----------------------------------------------------------------- projects

ACTIVITIES = [("HML Design Engineering", 900, 1500), ("HML Fabrication", 350, 650), ("HML Assembly and Testing", 400, 700),
	("HML Commissioning", 600, 1100)]

TASKS = [
	# subject, activity, budget hours, milestone %, start, end, assignees, status
	("Design and drawings", "HML Design Engineering", 80, 20, "2026-10-01", "2026-10-24", ["farhan"], "Completed"),
	("Frame fabrication and welding", "HML Fabrication", 160, 40, "2026-10-26", "2026-11-28", ["mahesh", "santosh"], "Working"),
	("Hydraulic assembly and test", "HML Assembly and Testing", 100, 30, "2026-11-30", "2026-12-20", ["santosh", "ravi"], "Open"),
	("Site commissioning", "HML Commissioning", 40, 10, "2027-01-05", "2027-01-15", ["suresh"], "Open"),
]


def step_project():
	if frappe.db.exists("Project", {"project_name": "Custom Hydraulic Test Rig - Northern Engineering"}):
		return
	from horizon_erp.setup.seed.phase1 import _ensure_hsn, _price

	for name, cost, bill in ACTIVITIES:
		get_or_insert("Activity Type", name, {"activity_type": name, "activity_type_name": name, "costing_rate": cost, "billing_rate": bill}, set_name=name)
	# milestone invoices bill a fraction (e.g. 0.2) of the contract line
	get_or_insert("UOM", "Lump Sum", {"uom_name": "Lump Sum", "must_be_whole_number": 0})
	if not frappe.db.exists("Item", "PRJ-TEST-RIG"):
		_ensure_hsn("998719")
		frappe.get_doc(
			{
				"doctype": "Item", "item_code": "PRJ-TEST-RIG", "item_name": "Custom Hydraulic Test Rig (engineered project)",
				"item_group": "Services", "stock_uom": "Lump Sum", "is_stock_item": 0, "is_sales_item": 1, "is_purchase_item": 0,
				"has_batch_no": 0, "has_expiry_date": 0, "gst_hsn_code": "998719",
				"item_defaults": [{"company": COMPANY, "default_warehouse": WH_RM, "income_account": acc("Project Revenue"), "selling_cost_center": cc("R&D")}],
			}
		).insert(set_name="PRJ-TEST-RIG", ignore_permissions=True)
		for pl in ("HML Standard Selling", "HML North Region Selling"):
			_price("PRJ-TEST-RIG", pl, 1800000, "Lump Sum")
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer_name("northern"),
			"company": COMPANY,
			"transaction_date": "2026-09-25",
			"delivery_date": "2027-01-31",
			"po_no": "NEW/CAPEX/2026/09",
			"po_date": "2026-09-25",
			"company_address": ADDRESS_MUMBAI,
			"selling_price_list": "HML North Region Selling",
			"items": [{"item_code": "PRJ-TEST-RIG", "qty": 1, "delivery_date": "2027-01-31"}],
			"payment_schedule": [],
		}
	)
	so.insert(ignore_permissions=True)
	so.submit()
	project = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": "Custom Hydraulic Test Rig - Northern Engineering",
			"company": COMPANY,
			"customer": so.customer,
			"sales_order": so.name,
			"expected_start_date": "2026-10-01",
			"expected_end_date": "2027-01-15",
			"estimated_costing": 1250000,
			"hml_overhead_pct": 15,
			"cost_center": cc("R&D"),
			"is_active": "Yes",
		}
	)
	project.insert(ignore_permissions=True)
	frappe.db.set_value("Sales Order", so.name, "project", project.name)
	log(f"+ Project {project.name} from SO {so.name} (contract Rs {so.base_net_total:,.0f})")
	for subject, activity, hours, pct, start, end, people, status in TASKS:
		task = frappe.get_doc(
			{
				"doctype": "Task",
				"subject": subject,
				"project": project.name,
				"exp_start_date": start,
				"exp_end_date": end,
				"expected_time": hours,
				"is_milestone": 1,
				"hml_billing_pct": pct,
				"hml_budgeted_cost": hours * next(a[1] for a in ACTIVITIES if a[0] == activity),
				"status": "Open",
			}
		)
		task.insert(ignore_permissions=True)
		for p in people:
			user = EMPLOYEES[p][12]
			if user:
				assign_to({"assign_to": [user_email(user)], "doctype": "Task", "name": task.name, "description": subject})
		log(f"+ Task {task.name} {subject}: {hours} h budget, milestone {pct} %")


def _task(subject):
	return frappe.db.get_value("Task", {"subject": subject, "project": ("like", "%")})


def step_timesheets():
	project = frappe.db.get_value("Project", {"project_name": "Custom Hydraulic Test Rig - Northern Engineering"})
	if frappe.db.exists("Timesheet", {"parent_project": project}) or frappe.db.exists("Timesheet Detail", {"project": project}):
		return
	plan = [
		# employee, task subject, activity, first day, days, hours/day, overtime day (date, hours)
		("farhan", "Design and drawings", "HML Design Engineering", "2026-10-05", 10, 8, ("2026-10-15", 10.5)),
		("mahesh", "Frame fabrication and welding", "HML Fabrication", "2026-10-26", 12, 6, ("2026-11-05", 10)),
		("santosh", "Frame fabrication and welding", "HML Fabrication", "2026-10-27", 10, 5, None),
	]
	for key, subject, activity, first, days, hpd, ot in plan:
		e = emp(key)
		logs = []
		count = 0
		for d in _workdays(first, add_days(first, 30)):
			if count >= days:
				break
			hours = ot[1] if ot and str(d) == ot[0] else hpd
			logs.append(
				{
					"activity_type": activity,
					"from_time": get_datetime(f"{d} 09:00:00"),
					"hours": hours,
					"to_time": frappe.utils.add_to_date(get_datetime(f"{d} 09:00:00"), hours=hours),
					"project": project,
					"task": _task(subject),
					"is_billable": 1,
				}
			)
			count += 1
		ts = frappe.get_doc({"doctype": "Timesheet", "company": COMPANY, "employee": e, "parent_project": project, "time_logs": logs})
		ts.insert(ignore_permissions=True)
		ts.submit()
		log(f"+ Timesheet {ts.name} {key}: {ts.total_hours} h, overtime {ts.hml_overtime_hours} h")

	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Issue",
			"company": COMPANY,
			"project": project,
			"set_posting_time": 1,
			"posting_date": "2026-10-28",
			"posting_time": "10:00:00",
			"items": [
				{"item_code": "RM-MS-PLATE-10", "qty": 650, "s_warehouse": WH_RM, "project": project, "cost_center": cc("R&D")},
				{"item_code": "RM-MS-CHANNEL-100", "qty": 300, "s_warehouse": WH_RM, "project": project, "cost_center": cc("R&D")},
				{"item_code": "CMP-CYL-100", "qty": 2, "s_warehouse": WH_RM, "project": project, "cost_center": cc("R&D")},
			],
		}
	)
	se.insert(ignore_permissions=True)
	se.submit()
	log(f"+ Material issued to project: {se.name} Rs {se.total_outgoing_value:,.0f}")

	# milestone 1 complete -> automatic invoice
	task = frappe.get_doc("Task", _task("Design and drawings"))
	task.status = "Completed"
	task.completed_on = "2026-10-24"
	task.completed_by = user_email("priya.nair")
	task.save(ignore_permissions=True)
	task.reload()
	fab = frappe.get_doc("Task", _task("Frame fabrication and welding"))
	fab.status = "Working"
	fab.progress = 55
	fab.save(ignore_permissions=True)
	p = frappe.get_doc("Project", project)
	p.save(ignore_permissions=True)
	log(f"+ Milestone invoice {task.hml_milestone_invoice}; project cost Rs {p.hml_total_cost:,.0f}, billed Rs {p.hml_billed_amount:,.0f}")


# ------------------------------------------------------------------- assets

CATEGORIES = [
	# name, fixed asset account, method, months, frequency, rate, shift_based
	("Production Equipment", "Plants and Machineries", "Straight Line", 120, 1, 0, 0),
	("Heavy Machinery (shift based)", "Capital Equipments", "Straight Line", 180, 1, 0, 1),
	("Vehicles", "Vehicles", "Written Down Value", 96, 1, 25, 0),
	("IT Equipment", "Electronic Equipments", "Straight Line", 36, 1, 0, 0),
]

EXISTING = [
	# name, category, gross, purchase date, booked months, accumulated, line
	("Line A Heavy Fabrication Line", "Production Equipment", 19000000, "2019-04-01", 84, 13300000, "HML Line A"),
	("Line B Assembly Line", "Production Equipment", 12000000, "2021-04-01", 60, 6000000, "HML Line B"),
	("Paint Booth with Oven", "Production Equipment", 6500000, "2020-04-01", 72, 3900000, "HML Line B"),
	("EOT Crane 10 T", "Heavy Machinery (shift based)", 4500000, "2018-04-01", 96, 2400000, "HML Line A"),
	("Shot Blasting Machine", "Production Equipment", 4000000, "2019-04-01", 84, 2800000, "HML Line A"),
	("Air Compressor 15 HP", "Production Equipment", 600000, "2017-04-01", 108, 540000, "HML Line A"),
]

NEW_ASSETS = [
	# item code, name, category, rate, date, supplier key, line
	("AST-PRESS-BRAKE", "CNC Press Brake 160 T", "Production Equipment", 4200000, "2026-04-20", "precision", "HML Line A"),
	("AST-WELD-ROBOT", "Robotic MIG Welding Cell", "Heavy Machinery (shift based)", 2800000, "2026-06-10", "delhielec", "HML Line A"),
	("AST-FORKLIFT", "Diesel Forklift 3 T", "Vehicles", 1400000, "2026-05-15", "bharat", None),
	("AST-LAPTOP", "Engineering Laptop (CAD)", "IT Equipment", 160000, "2026-07-01", "delhielec", None),
]


def step_asset_masters():
	for loc in ("HML Mumbai Plant", "HML Delhi DC"):
		get_or_insert("Location", loc, {"location_name": loc})
	get_or_insert("Item Group", "HML Fixed Assets", {"item_group_name": "HML Fixed Assets", "parent_item_group": "All Item Groups"})
	for name, account, method, months, freq, rate, shift in CATEGORIES:
		if frappe.db.exists("Asset Category", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Asset Category",
				"asset_category_name": name,
				"accounts": [{
					"company_name": COMPANY,
					"fixed_asset_account": acc(account),
					"accumulated_depreciation_account": acc("Accumulated Depreciations"),
					"depreciation_expense_account": acc("Depreciation"),
				}],
				"finance_books": [{
					"depreciation_method": method,
					"total_number_of_depreciations": months,
					"frequency_of_depreciation": freq,
					"rate_of_depreciation": rate or None,
					"shift_based": shift,
				}],
			}
		).insert(ignore_permissions=True)
		log(f"+ Asset Category {name}: {method}, {months} months{' (shift based)' if shift else ''}")
	if not frappe.db.exists("Asset Shift Factor", "Double Shift"):
		for nm, factor, default in (("Single Shift", 1, 0), ("Double Shift", 1.5, 1), ("Triple Shift", 2, 0)):
			get_or_insert("Asset Shift Factor", nm, {"shift_name": nm, "shift_factor": factor, "default": default})
	from horizon_erp.setup.seed.phase1 import _ensure_hsn

	_ensure_hsn("84622910")
	for code, name, category, _rate, _d, _s, _l in NEW_ASSETS + [("AST-EXISTING-PLANT", "Existing plant and machinery", "Production Equipment", 0, 0, 0, 0)]:
		if frappe.db.exists("Item", code):
			continue
		frappe.get_doc(
			{
				"doctype": "Item", "item_code": code, "item_name": name, "item_group": "HML Fixed Assets", "stock_uom": "Nos",
				"is_stock_item": 0, "is_fixed_asset": 1, "asset_category": category, "auto_create_assets": 1,
				"asset_naming_series": "ACC-ASS-.YYYY.-", "is_purchase_item": 1, "is_sales_item": 1, "has_batch_no": 0,
				"has_expiry_date": 0, "gst_hsn_code": "84622910",
				"item_defaults": [{"company": COMPANY, "default_warehouse": WH_RM, "buying_cost_center": cc("Mfg - Equipment")}],
			}
		).insert(set_name=code, ignore_permissions=True)


def _asset_common(name, category, line):
	return {
		"asset_name": name,
		"asset_category": category,
		"company": COMPANY,
		"location": "HML Mumbai Plant",
		"cost_center": cc("Mfg - Equipment"),
		"hml_production_line": line,
		"calculate_depreciation": 1,
		"insurer": "New India Assurance Co Ltd",
		"policy_number": f"NIA/FIRE/26/{zlib.crc32(name.encode()) % 100000:05d}",
		"insurance_start_date": "2026-04-01",
		"insurance_end_date": "2027-03-31",
		"maintenance_required": 1,
	}


def step_existing_assets():
	for name, category, gross, date, booked, accumulated, line in EXISTING:
		if frappe.db.exists("Asset", {"asset_name": name, "company": COMPANY}):
			continue
		cat = frappe.get_doc("Asset Category", category).finance_books[0]
		asset = frappe.get_doc(
			{
				"doctype": "Asset",
				"item_code": "AST-EXISTING-PLANT",
				**_asset_common(name, category, line),
				"is_existing_asset": 1,
				"purchase_date": date,
				"available_for_use_date": date,
				"gross_purchase_amount": gross,
				"purchase_amount": gross,
				"opening_accumulated_depreciation": accumulated,
				"opening_number_of_booked_depreciations": booked,
				"finance_books": [{
					"depreciation_method": cat.depreciation_method,
					"total_number_of_depreciations": cat.total_number_of_depreciations,
					"frequency_of_depreciation": 1,
					"depreciation_start_date": "2026-04-30",
					"shift_based": cat.shift_based,
				}],
			}
		)
		asset.insert(ignore_permissions=True)
		asset.submit()
		log(f"+ Existing asset {asset.name} {name}: gross Rs {gross:,.0f}, NBV Rs {gross - accumulated:,.0f}")


def step_new_assets():
	from horizon_erp.setup.seed.phase1 import supplier_name

	for code, name, category, rate, date, sup, line in NEW_ASSETS:
		if frappe.db.exists("Purchase Invoice Item", {"item_code": code, "docstatus": 1}):
			continue
		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": COMPANY,
				"supplier": supplier_name(sup),
				"posting_date": date,
				"set_posting_time": 1,
				"bill_no": f"INV-{code}",
				"bill_date": date,
				"update_stock": 0,
				"billing_address": ADDRESS_MUMBAI,
				"items": [{"item_code": code, "qty": 1, "rate": rate, "cost_center": cc("Mfg - Equipment")}],
			}
		)
		pi.insert(ignore_permissions=True)
		pi.submit()
		# ERPNext auto-creates assets only from receipts (update_stock); for a
		# bill-only purchase the asset is created against the invoice line
		asset = frappe.get_doc(
			{
				"doctype": "Asset",
				"item_code": code,
				"purchase_invoice": pi.name,
				"purchase_invoice_item": pi.items[0].name,
				"supplier": pi.supplier,
				"gross_purchase_amount": pi.items[0].base_net_amount,
				"purchase_amount": pi.items[0].base_net_amount,
				"asset_quantity": 1,
			}
		)
		asset.update(_asset_common(name, category, line))
		asset.available_for_use_date = date
		asset.purchase_date = date
		cat = frappe.get_doc("Asset Category", category).finance_books[0]
		asset.set("finance_books", [{
			"depreciation_method": cat.depreciation_method,
			"total_number_of_depreciations": cat.total_number_of_depreciations,
			"frequency_of_depreciation": 1,
			"rate_of_depreciation": cat.rate_of_depreciation,
			"depreciation_start_date": frappe.utils.get_last_day(date),
			"shift_based": cat.shift_based,
		}])
		asset.insert(ignore_permissions=True)
		asset.submit()
		gl = frappe.get_all("GL Entry", filters={"voucher_no": pi.name, "is_cancelled": 0}, fields=["account", "debit", "credit"])
		log(f"+ {name}: PI {pi.name} capitalised as {asset.name}; GL {[(g.account, g.debit or -g.credit) for g in gl]}")


def step_depreciation():
	from erpnext.assets.doctype.asset.depreciation import post_depreciation_entries

	before = frappe.db.count("Journal Entry", {"company": COMPANY, "voucher_type": "Depreciation Entry", "docstatus": 1})
	post_depreciation_entries(date="2026-11-18")
	after = frappe.db.count("Journal Entry", {"company": COMPANY, "voucher_type": "Depreciation Entry", "docstatus": 1})
	log(f"+ Depreciation entries posted Apr-Oct 2026: {after - before}")


def step_maintenance_and_disposal():
	if frappe.db.exists("Maintenance Job", {"docstatus": 1}):
		return
	def asset_by(name):
		return frappe.db.get_value("Asset", {"asset_name": name, "company": COMPANY})

	jobs = [
		("CNC Press Brake 160 T", "Planned", "2026-09-12", 2, "Vendor", "precision", "6-monthly hydraulic oil and filter change, back-gauge calibration", 18000, 9500),
		("Robotic MIG Welding Cell", "Reactive (Breakdown)", "2026-10-08", 14, "Vendor", "delhielec", "Torch cable failure and wire feeder motor burnt", 22000, 26000),
		("EOT Crane 10 T", "Planned", "2026-08-20", 4, "In-house", None, "Statutory load test and wire rope inspection", 12000, 4500),
		("Air Compressor 15 HP", "Reactive (Breakdown)", "2026-07-02", 10, "Vendor", "bharat", "Crankshaft bearing seizure, rewound motor", 28000, 31000),
		("Air Compressor 15 HP", "Reactive (Breakdown)", "2026-09-22", 8, "Vendor", "bharat", "Valve plate failure, oil carry-over", 14000, 19000),
	]
	from horizon_erp.setup.seed.phase1 import supplier_name

	for asset_name, mtype, date, downtime, by, vendor, desc, labour, parts in jobs:
		mj = frappe.get_doc(
			{
				"doctype": "Maintenance Job",
				"asset": asset_by(asset_name),
				"maintenance_type": mtype,
				"job_date": date,
				"downtime_hours": downtime,
				"performed_by": by,
				"vendor": supplier_name(vendor) if vendor else None,
				"description": desc,
				"work_done": "Completed and tested",
				"labour_cost": labour,
				"parts_cost": parts,
				"expense_account": acc("Repairs and Maintenance - Plant"),
				"payment_account": acc("HDFC Bank - Current Account"),
			}
		)
		mj.insert(ignore_permissions=True)
		mj.submit()
	log(f"+ {len(jobs)} maintenance jobs booked")

	buyer = frappe.db.get_value("Customer", {"customer_name": "Om Scrap Traders"})
	if not buyer:
		buyer = frappe.get_doc(
			{
				"doctype": "Customer", "customer_name": "Om Scrap Traders", "customer_type": "Company", "customer_group": "Standard",
				"territory": "Maharashtra", "gst_category": "Unregistered", "tax_category": "GST by Place of Supply",
				"custom_customer": [{"company": COMPANY}],
			}
		).insert(ignore_permissions=True).name
		frappe.get_doc(
			{"doctype": "Address", "address_title": "Om Scrap Traders", "address_type": "Billing", "address_line1": "Shed 7, Kurla",
				"city": "Mumbai", "state": "Maharashtra", "pincode": "400070", "country": "India", "gst_category": "Unregistered",
				"links": [{"link_doctype": "Customer", "link_name": buyer}]}
		).insert(ignore_permissions=True)
	from horizon_erp.overrides.assets import retire_asset

	res = retire_asset(
		asset_by("Air Compressor 15 HP"),
		"Sell",
		"2026-11-15",
		"Two breakdowns in 3 months (Rs 92 K repairs, 20 % of original cost); replaced by a screw compressor on lease.",
		salvage_value=45000,
		customer=buyer,
	)
	si = res["sales_invoice"]
	gl = frappe.get_all("GL Entry", filters={"voucher_no": si, "is_cancelled": 0}, fields=["account", "debit", "credit"])
	log(f"+ Compressor sold via {si}: {[(g.account, g.debit or -g.credit) for g in gl]}")


STEPS = [
	("accounts", step_accounts),
	("holidays_and_shifts", step_holidays_and_shifts),
	("leave_setup", step_leave_setup),
	("employees", step_employees),
	("shift_assignments", step_shift_assignments),
	("leave_allocation", step_leave_allocation),
	("october_attendance", step_october_attendance),
	("november_checkins", step_november_checkins),
	("leave_applications", step_leave_applications),
	("payroll_masters", step_payroll_masters),
	("salary_assignments", step_salary_assignments),
	("payroll_run", step_payroll_run),
	("project", step_project),
	("timesheets", step_timesheets),
	("asset_masters", step_asset_masters),
	("existing_assets", step_existing_assets),
	("new_assets", step_new_assets),
	("depreciation", step_depreciation),
	("maintenance_and_disposal", step_maintenance_and_disposal),
]
