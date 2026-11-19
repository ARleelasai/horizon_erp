"""Phase 1 - Setup & masters for Horizon Manufacturing Ltd.

Company, GST registrations, Location dimension defaults, cost centers,
chart-of-accounts additions, warehouse tree, item groups, territories,
customer/supplier groups, price lists, customers, suppliers, items, roles,
users, user permissions, opening stock and recurring journals.
"""

import zlib

import frappe
from frappe.utils import add_months, get_last_day, getdate

from horizon_erp.constants import (
	ABBR,
	ADDRESS_DELHI,
	ADDRESS_MUMBAI,
	BRANCH_DELHI,
	BRANCH_MUMBAI,
	CATEGORY_COST_CENTER,
	COMPANY,
	COMPANY_ID,
	GSTIN_DELHI,
	GSTIN_MUMBAI,
	IG_COMPONENTS,
	IG_EQUIPMENT,
	IG_RAW,
	IG_SPARES,
	IG_SUBASSY,
	PAN,
	ROLE_DEPT_HEAD,
	ROLE_FD,
	ROLE_HR,
	ROLE_OPS,
	ROLE_PROC,
	ROLE_QI,
	ROLE_SALES_DIR,
	ROLE_SALES_MGR,
	ROLE_SALES_USER,
	ROLE_WH_MGR,
	WH_DELHI,
	WH_DELHI_FG,
	WH_FG,
	WH_MUMBAI,
	WH_QC,
	WH_REJECTED,
	WH_RM,
	WH_ROOT,
	WH_SCRAP,
	WH_TRANSIT,
	WH_WIP,
	acc,
	cc,
	wh,
)
from horizon_erp.setup.seed.guards import original_tax_setup
from horizon_erp.setup.seed.utils import ensure_value, get_or_insert, gstin, log, set_posting

OPENING_DATE = "2026-04-01"
AUTO_TAX_CATEGORY = "GST by Place of Supply"
TEST_PASSWORD = "Horizon@2026"
EMAIL_DOMAIN = "horizonmfg.test"

# ------------------------------------------------------------------ company


def step_company():
	if frappe.db.exists("Company", COMPANY):
		log("company exists")
	else:
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": COMPANY,
				"abbr": ABBR,
				"country": "India",
				"default_currency": "INR",
				"create_chart_of_accounts_based_on": "Standard Template",
				"chart_of_accounts": "India - Chart of Accounts",
				"custom_company_id": COMPANY_ID,
				"gstin": GSTIN_MUMBAI,
				"pan": PAN,
				"gst_category": "Registered Regular",
				"default_gst_rate": "18.0",
				"enable_perpetual_inventory": 1,
				"phone_no": "+91 22 4000 5000",
				"email": f"accounts@{EMAIL_DOMAIN}",
				"date_of_incorporation": "2009-06-15",
			}
		)
		# Stock ERPNext/India Compliance tax setup instead of the agrica_dms patch
		with original_tax_setup():
			company.insert(ignore_permissions=True)
		log(f"+ Company: {COMPANY}")

	for fy in frappe.get_all("Fiscal Year", filters={"year_start_date": (">=", "2024-04-01")}, pluck="name"):
		doc = frappe.get_doc("Fiscal Year", fy)
		if doc.companies and COMPANY not in [r.company for r in doc.companies]:
			doc.append("companies", {"company": COMPANY})
			doc.save(ignore_permissions=True)
			log(f"~ Fiscal Year {fy}: + {COMPANY}")


def step_gst_registrations():
	addresses = [
		(
			ADDRESS_MUMBAI,
			{
				"address_title": "HML Mumbai HQ",
				"address_type": "Billing",
				"address_line1": "Plot 14, MIDC Industrial Area",
				"address_line2": "Andheri East",
				"city": "Mumbai",
				"state": "Maharashtra",
				"pincode": "400093",
				"country": "India",
				"gstin": GSTIN_MUMBAI,
				"gst_category": "Registered Regular",
				"is_your_company_address": 1,
				"is_primary_address": 1,
				"email_id": f"mumbai@{EMAIL_DOMAIN}",
				"phone": "+91 22 4000 5000",
			},
		),
		(
			ADDRESS_DELHI,
			{
				"address_title": "HML Delhi DC",
				"address_type": "Billing",
				"address_line1": "Khasra 221, Mundka Industrial Area",
				"city": "New Delhi",
				"state": "Delhi",
				"pincode": "110041",
				"country": "India",
				"gstin": GSTIN_DELHI,
				"gst_category": "Registered Regular",
				"is_your_company_address": 1,
				"email_id": f"delhi@{EMAIL_DOMAIN}",
				"phone": "+91 11 4100 6000",
			},
		),
	]
	for name, values in addresses:
		if frappe.db.exists("Address", name):
			continue
		doc = frappe.get_doc({"doctype": "Address", **values})
		doc.append("links", {"link_doctype": "Company", "link_name": COMPANY})
		doc.insert(ignore_permissions=True)
		log(f"+ Address: {doc.name}")

	accounts = frappe.get_all("GST Account", filters={"company": COMPANY}, fields=["account_type"])
	log(f"GST Settings accounts for HML: {sorted({a.account_type for a in accounts})}")
	if not accounts:
		frappe.throw("GST accounts missing for HML in GST Settings")


def step_location_dimension():
	dim = frappe.get_doc("Accounting Dimension", {"document_type": "Branch"})
	if not [d for d in dim.dimension_defaults if d.company == COMPANY]:
		dim.append(
			"dimension_defaults",
			{
				"company": COMPANY,
				"reference_document": "Branch",
				"default_dimension": BRANCH_MUMBAI,
				"mandatory_for_bs": 0,
				"mandatory_for_pl": 1,
			},
		)
		dim.save(ignore_permissions=True)
		log("~ Accounting Dimension Branch: HML default HQ Mumbai, mandatory for P&L")


# ------------------------------------------------------------ cost centers

COST_CENTERS = [
	# (name, parent, is_group)
	("Manufacturing", None, 1),
	("Mfg - Equipment", "Manufacturing", 0),
	("Mfg - Spares", "Manufacturing", 0),
	("Mfg - Components", "Manufacturing", 0),
	("Sales", None, 0),
	("R&D", None, 0),
]


def step_cost_centers():
	root = frappe.db.get_value("Cost Center", {"company": COMPANY, "is_group": 1, "parent_cost_center": ""})
	root = root or cc(COMPANY)
	if frappe.db.exists("Cost Center", cc("Main")) and not frappe.db.exists("Cost Center", cc("Admin")):
		frappe.rename_doc("Cost Center", cc("Main"), cc("Admin"), force=True)
		frappe.db.set_value("Cost Center", cc("Admin"), "cost_center_name", "Admin")
		log("~ Cost Center Main - HML renamed to Admin - HML")
	for name, parent, is_group in COST_CENTERS:
		get_or_insert(
			"Cost Center",
			cc(name),
			{
				"cost_center_name": name,
				"parent_cost_center": cc(parent) if parent else root,
				"company": COMPANY,
				"is_group": is_group,
			},
		)
	ensure_value("Company", COMPANY, {"cost_center": cc("Admin"), "round_off_cost_center": cc("Admin")})


# ----------------------------------------------------------------- accounts

ACCOUNTS = [
	# (account_name, parent account_name, account_type)
	("Sales - Equipment", "Direct Income", "Income Account"),
	("Sales - Spares", "Direct Income", "Income Account"),
	("Sales - Components", "Direct Income", "Income Account"),
	("Project Revenue", "Direct Income", "Income Account"),
	("Manufacturing Wages", "Direct Expenses", ""),
	("Contract Labour Charges", "Direct Expenses", ""),
	("Rework Cost", "Direct Expenses", ""),
	("Factory Power and Fuel", "Direct Expenses", ""),
	("Factory Rent", "Indirect Expenses", ""),
	("Warehouse Rent", "Indirect Expenses", ""),
	("Repairs and Maintenance - Plant", "Indirect Expenses", ""),
	("Insurance Expense", "Indirect Expenses", ""),
	("R&D Expenses", "Indirect Expenses", ""),
	("Scrap and Obsolescence Loss", "Indirect Expenses", ""),
	("Employer PF Contribution", "Indirect Expenses", ""),
	("Employer ESI Contribution", "Indirect Expenses", ""),
	("PF Payable", "Duties and Taxes", "Tax"),
	("ESI Payable", "Duties and Taxes", "Tax"),
	("Professional Tax Payable", "Duties and Taxes", "Tax"),
	("TDS on Salary Payable", "Duties and Taxes", "Tax"),
	("HDFC Bank - Current Account", "Bank Accounts", "Bank"),
	("Unrealised Profit on Branch Transfer", "Current Liabilities", ""),
]


def step_accounts():
	"""Extra heads; see design doc section 2 for the account map."""
	for name, parent, account_type in ACCOUNTS:
		get_or_insert(
			"Account",
			acc(name),
			{
				"account_name": name,
				"parent_account": acc(parent),
				"company": COMPANY,
				"is_group": 0,
				"account_type": account_type,
			},
		)
	# Branch transfers are priced at cost, so this stays at zero; ERPNext still
	# requires the account for internal (same-company) invoices.
	ensure_value("Company", COMPANY, {"unrealized_profit_loss_account": acc("Unrealised Profit on Branch Transfer")})


# --------------------------------------------------------------- warehouses


def step_warehouses():
	renames = {
		wh("Stores"): WH_RM,
		wh("Work In Progress"): WH_WIP,
		wh("Finished Goods"): WH_FG,
	}
	for old, new in renames.items():
		if frappe.db.exists("Warehouse", old) and not frappe.db.exists("Warehouse", new):
			frappe.rename_doc("Warehouse", old, new, force=True)
			frappe.db.set_value("Warehouse", new, "warehouse_name", new.rsplit(f" - {ABBR}", 1)[0])
			log(f"~ Warehouse {old} -> {new}")

	def group(name):
		return get_or_insert(
			"Warehouse",
			wh(name),
			{"warehouse_name": name, "is_group": 1, "parent_warehouse": WH_ROOT, "company": COMPANY},
		)

	group("Mumbai HQ")
	group("Delhi DC")

	leaves = [
		(WH_RM, WH_MUMBAI),
		(WH_FG, WH_MUMBAI),
		(WH_WIP, WH_MUMBAI),
		(WH_QC, WH_MUMBAI),
		(WH_REJECTED, WH_MUMBAI),
		(WH_SCRAP, WH_MUMBAI),
		(WH_DELHI_FG, WH_DELHI),
	]
	for name, parent in leaves:
		if frappe.db.exists("Warehouse", name):
			if frappe.db.get_value("Warehouse", name, "parent_warehouse") != parent:
				ensure_value("Warehouse", name, {"parent_warehouse": parent})
			continue
		get_or_insert(
			"Warehouse",
			name,
			{
				"warehouse_name": name.rsplit(f" - {ABBR}", 1)[0],
				"is_group": 0,
				"parent_warehouse": parent,
				"company": COMPANY,
			},
		)

	ensure_value(
		"Company",
		COMPANY,
		{
			"default_in_transit_warehouse": WH_TRANSIT,
		},
	)


# ---------------------------------------------------- groups and territories


def step_groups():
	# Customer.tax_category is mandatory on this site. A category with no tax
	# templates lets India Compliance pick CGST+SGST or IGST from place of
	# supply vs the selling GSTIN (Mumbai or Delhi), instead of pinning one.
	get_or_insert("Tax Category", AUTO_TAX_CATEGORY, {"title": AUTO_TAX_CATEGORY})

	for name, parent in [
		(IG_EQUIPMENT, "All Item Groups"),
		(IG_SPARES, "All Item Groups"),
		(IG_COMPONENTS, "All Item Groups"),
		(IG_RAW, "All Item Groups"),
		(IG_SUBASSY, "All Item Groups"),
	]:
		get_or_insert("Item Group", name, {"item_group_name": name, "parent_item_group": parent})

	# GST rates by category (rates as given in the assignment brief)
	group_tax = {
		IG_EQUIPMENT: 5,
		IG_SPARES: 12,
		IG_COMPONENTS: 5,
		IG_RAW: 18,
		IG_SUBASSY: 18,
	}
	for group, rate in group_tax.items():
		doc = frappe.get_doc("Item Group", group)
		template = f"GST {rate}% - {ABBR}"
		# ERPNext matches item tax rows on the document's tax category; India
		# Compliance sets that to In-State / Out-State, so one row per category
		# (the template itself carries both CGST+SGST and IGST lines).
		changed = False
		for category in (
			"",
			AUTO_TAX_CATEGORY,
			"In-State",
			"Out-State",
			"Reverse Charge In-State",
			"Reverse Charge Out-State",
		):
			if not [t for t in doc.get("taxes") if t.item_tax_template == template and (t.tax_category or "") == category]:
				doc.append("taxes", {"item_tax_template": template, "tax_category": category or None})
				changed = True
		if changed:
			doc.save(ignore_permissions=True)
			log(f"~ Item Group {group}: {template}")

	for name, parent, is_group in [
		("HML West", "India", 1),
		("HML North", "India", 1),
		("HML South", "India", 1),
		("Maharashtra", "HML West", 0),
		("Gujarat", "HML West", 0),
		("Delhi NCR", "HML North", 0),
		("Karnataka", "HML South", 0),
	]:
		get_or_insert(
			"Territory",
			name,
			{"territory_name": name, "parent_territory": parent, "is_group": is_group},
		)

	for name in ("Premium", "Standard"):
		get_or_insert(
			"Customer Group",
			name,
			{"customer_group_name": name, "parent_customer_group": "All Customer Groups", "is_group": 0},
		)
	get_or_insert(
		"Customer Group",
		"Internal (HML)",
		{"customer_group_name": "Internal (HML)", "parent_customer_group": "All Customer Groups"},
	)
	for name in ("Hydraulics", "Internal (HML)"):
		get_or_insert(
			"Supplier Group",
			name,
			{"supplier_group_name": name, "parent_supplier_group": "All Supplier Groups"},
		)


def step_price_lists():
	for name, selling, buying in [
		("HML Standard Selling", 1, 0),
		("HML North Region Selling", 1, 0),
		("HML Standard Buying", 0, 1),
	]:
		get_or_insert(
			"Price List",
			name,
			{"price_list_name": name, "currency": "INR", "selling": selling, "buying": buying, "enabled": 1},
		)


# -------------------------------------------------------- parties (master data)

# key: (name, group, territory, state, city, pincode, pan or None, extra)
CUSTOMERS = {
	"apex": ("Apex Infra Projects Pvt Ltd", "Premium", "Maharashtra", "Maharashtra", "Pune", "411018", "AAFCA4521K"),
	"northern": ("Northern Engineering Works", "Premium", "Delhi NCR", "Delhi", "New Delhi", "110020", "AACFN7788L"),
	"deccan": ("Deccan Fabricators", "Standard", "Karnataka", "Karnataka", "Bengaluru", "560058", "AAFCD3344M"),
	"sahyadri": ("Sahyadri Agro Industries", "Standard", "Maharashtra", "Maharashtra", "Nashik", "422007", "AAKCS9087P"),
	"capital": ("Capital Machinery Traders", "Standard", "Delhi NCR", "Delhi", "New Delhi", "110015", "AAJFC5566Q"),
	"abc": ("ABC Corp", "Standard", "Maharashtra", "Maharashtra", "Thane", "400604", "AABCA1122R"),
	"gujarat": ("Gujarat Pump Works", "Premium", "Gujarat", "Gujarat", "Ahmedabad", "382445", "AAGCG7700S"),
	"konkan": ("Konkan Steel Structures", "Standard", "Maharashtra", "Maharashtra", "Ratnagiri", "415612", None),
}

SUPPLIERS = {
	"bharat": ("Bharat Steel Suppliers", "Raw Material", "Maharashtra", "Mumbai", "400072", "AABCB2345C"),
	"precision": ("Precision Bearings Co", "Hardware", "Gujarat", "Rajkot", "360004", "AAECP6789D"),
	"delhielec": ("Delhi Electricals & Drives", "Electrical", "Delhi", "New Delhi", "110028", "AAFCD1357E"),
	"abcsupplies": ("ABC Supplies", "Hardware", "Maharashtra", "Bhiwandi", "421302", "AABCA9753F"),
	"abc": ("ABC Corp", "Hardware", "Maharashtra", "Thane", "400604", "AABCA1122R"),
	"shree": ("Shree Fasteners", "Hardware", "Maharashtra", "Vasai", "401208", None),
	"rapid": ("Rapid Paints & Coatings", "Raw Material", "Maharashtra", "Navi Mumbai", "400705", "AAFCR2468G"),
	"hydrotech": ("Hydro-Tech Components", "Hydraulics", "Karnataka", "Bengaluru", "560099", "AAGCH8642H"),
}

STATE_CODES = {"Maharashtra": "27", "Delhi": "07", "Karnataka": "29", "Gujarat": "24"}


def _party_gstin(state, pan):
	return gstin(STATE_CODES[state], pan) if pan else None


def _make_party_address(party_type, party_name, display, state, city, pincode, gstin_no):
	title = f"{display}-Billing"
	if frappe.db.exists("Address", {"address_title": display, "address_type": "Billing"}):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": display,
			"address_type": "Billing",
			"address_line1": f"{display} Office",
			"city": city,
			"state": state,
			"pincode": pincode,
			"country": "India",
			"gstin": gstin_no or "",
			"gst_category": "Registered Regular" if gstin_no else "Unregistered",
			"is_primary_address": 1,
			"is_shipping_address": 1,
			"links": [{"link_doctype": party_type, "link_name": party_name}],
		}
	)
	doc.insert(ignore_permissions=True)
	log(f"+ Address: {doc.name} ({title})")


def _make_contact(party_type, party_name, first, last, email, phone):
	if frappe.db.exists("Contact", {"email_id": email}):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": first,
			"last_name": last,
			"email_ids": [{"email_id": email, "is_primary": 1}],
			"phone_nos": [{"phone": phone, "is_primary_mobile_no": 1}],
			"links": [{"link_doctype": party_type, "link_name": party_name}],
		}
	)
	doc.insert(ignore_permissions=True)


def customer_name(key):
	return frappe.db.get_value("Customer", {"customer_name": CUSTOMERS[key][0]})


def supplier_name(key):
	return frappe.db.get_value("Supplier", {"supplier_name": SUPPLIERS[key][0]})


def step_customers():
	for key, (name, group, territory, state, city, pincode, pan) in CUSTOMERS.items():
		gst_no = _party_gstin(state, pan)
		existing = frappe.db.get_value("Customer", {"customer_name": name})
		if not existing:
			doc = frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": name,
					"customer_type": "Company",
					"customer_group": group,
					"territory": territory,
					"gstin": gst_no or "",
					"pan": pan or "",
					"gst_category": "Registered Regular" if gst_no else "Unregistered",
					"tax_category": AUTO_TAX_CATEGORY,
					"default_price_list": "HML North Region Selling"
					if state == "Delhi"
					else "HML Standard Selling",
					"payment_terms": "",
					"custom_customer": [{"company": COMPANY}],
					"credit_limits": [{"company": COMPANY, "credit_limit": 2500000 if group == "Premium" else 1000000}],
				}
			)
			doc.insert(ignore_permissions=True)
			existing = doc.name
			log(f"+ Customer: {existing} {name}")
		elif frappe.db.get_value("Customer", existing, "tax_category") != AUTO_TAX_CATEGORY:
			frappe.db.set_value("Customer", existing, "tax_category", AUTO_TAX_CATEGORY)
		_make_party_address("Customer", existing, name, state, city, pincode, gst_no)
		first = name.split()[0]
		_make_contact("Customer", existing, first, "Purchase", f"purchase@{key}.example.com", "+91 98200 1" + str(zlib.crc32(key.encode()) % 10000).zfill(4))


def step_suppliers():
	for key, (name, group, state, city, pincode, pan) in SUPPLIERS.items():
		gst_no = _party_gstin(state, pan)
		existing = frappe.db.get_value("Supplier", {"supplier_name": name})
		if not existing:
			values = {
				"doctype": "Supplier",
				"supplier_name": name,
				"supplier_type": "Company",
				"supplier_group": group,
				"country": "India",
				"gstin": gst_no or "",
				"pan": pan or "",
				"gst_category": "Registered Regular" if gst_no else "Unregistered",
				"default_price_list": "HML Standard Buying",
			}
			if key == "abcsupplies":
				values.update(
					{
						"hml_is_blacklisted": 1,
						"hml_blacklisted_on": "2026-06-30",
						"hml_blacklist_reason": "Q1 FY26-27: 3 consecutive lots of hydraulic seals failed pressure test "
						"(NCR-2026-014/017/021). Sole source for HX-500 custom manifold block, so exceptions "
						"are allowed with Finance Director approval.",
					}
				)
			doc = frappe.get_doc(values)
			doc.insert(ignore_permissions=True)
			existing = doc.name
			log(f"+ Supplier: {existing} {name}")
		_make_party_address("Supplier", existing, f"{name} (Supplier)" if key == "abc" else name, state, city, pincode, gst_no)
		_make_contact("Supplier", existing, name.split()[0], "Sales", f"sales@{key}-supplier.example.com", "+91 98190 2" + str(zlib.crc32(key.encode()) % 10000).zfill(4))

	# ABC Corp is both customer and supplier: link them for netting (Party Link)
	cust, supp = customer_name("abc"), supplier_name("abc")
	if cust and supp and not frappe.db.exists("Party Link", {"primary_party": cust, "secondary_party": supp}):
		frappe.get_doc(
			{
				"doctype": "Party Link",
				"primary_role": "Customer",
				"primary_party": cust,
				"secondary_role": "Supplier",
				"secondary_party": supp,
			}
		).insert(ignore_permissions=True)
		log("+ Party Link ABC Corp customer <-> supplier")


def step_internal_parties():
	"""Branch-transfer parties: Mumbai ships to 'HML Delhi DC (Internal)'."""
	cust = frappe.db.get_value("Customer", {"customer_name": "HML Delhi DC (Internal)"})
	if not cust:
		doc = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "HML Delhi DC (Internal)",
				"customer_type": "Company",
				"customer_group": "Internal (HML)",
				"territory": "Delhi NCR",
				"is_internal_customer": 1,
				"represents_company": COMPANY,
				"companies": [{"company": COMPANY}],
				"gstin": GSTIN_DELHI,
				"gst_category": "Registered Regular",
				"tax_category": AUTO_TAX_CATEGORY,
				"custom_customer": [{"company": COMPANY}],
			}
		)
		doc.insert(ignore_permissions=True)
		cust = doc.name
		log(f"+ Internal Customer: {cust}")
	_add_link(ADDRESS_DELHI, "Customer", cust)

	supp = frappe.db.get_value("Supplier", {"supplier_name": "HML Mumbai HQ (Internal)"})
	if not supp:
		doc = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "HML Mumbai HQ (Internal)",
				"supplier_type": "Company",
				"supplier_group": "Internal (HML)",
				"country": "India",
				"is_internal_supplier": 1,
				"represents_company": COMPANY,
				"companies": [{"company": COMPANY}],
				"gstin": GSTIN_MUMBAI,
				"gst_category": "Registered Regular",
			}
		)
		doc.insert(ignore_permissions=True)
		supp = doc.name
		log(f"+ Internal Supplier: {supp}")
	_add_link(ADDRESS_MUMBAI, "Supplier", supp)


def _add_link(address, link_doctype, link_name):
	doc = frappe.get_doc("Address", address)
	if not [l for l in doc.links if l.link_doctype == link_doctype and l.link_name == link_name]:
		doc.append("links", {"link_doctype": link_doctype, "link_name": link_name})
		doc.save(ignore_permissions=True)


# -------------------------------------------------------------------- items

# code: (name, group, uom, hsn, valuation/buy rate, selling rate, kind, extra)
#   kind: fg (made, sold), sa (made), buy (bought), buysell (bought and sold)
ITEMS = {
	# Finished equipment
	"HX-500": ("HX-500 Hydraulic Press (50 T)", IG_EQUIPMENT, "Nos", "84622910", 0, 450000, "fg",
		dict(has_serial_no=1, serial_no_series="HX5-.#####", hml_machine_hours_per_unit=6, hml_eligible_lines="Line A",
			hml_mfg_lead_time_days=12, hml_make_to_stock=0, hml_criticality="A - Critical", hml_abc_class="A",
			hml_demand_pattern="Stable")),
	"CX-200": ("CX-200 Belt Conveyor Unit (6 m)", IG_EQUIPMENT, "Nos", "84283300", 0, 185000, "fg",
		dict(has_serial_no=1, serial_no_series="CX2-.#####", hml_machine_hours_per_unit=3, hml_eligible_lines="Any",
			hml_mfg_lead_time_days=7, hml_make_to_stock=1, hml_criticality="B - Important", hml_abc_class="A",
			hml_demand_pattern="Stable")),
	# Sub-assemblies (level 2)
	"SA-HX-FRAME": ("HX-500 Welded Main Frame", IG_SUBASSY, "Nos", "84669400", 0, 0, "sa",
		dict(hml_machine_hours_per_unit=2.5, hml_eligible_lines="Line A", hml_mfg_lead_time_days=4)),
	"SA-HX-HPU": ("HX-500 Hydraulic Power Unit", IG_SUBASSY, "Nos", "84122100", 0, 0, "sa",
		dict(hml_machine_hours_per_unit=1.5, hml_eligible_lines="Any", hml_mfg_lead_time_days=3)),
	"SA-HX-CTRL": ("HX-500 Control Panel", IG_SUBASSY, "Nos", "85371000", 0, 0, "sa",
		dict(hml_machine_hours_per_unit=1, hml_eligible_lines="Any", hml_mfg_lead_time_days=2)),
	"SA-CX-FRAME": ("CX-200 Conveyor Frame", IG_SUBASSY, "Nos", "84289090", 0, 0, "sa",
		dict(hml_machine_hours_per_unit=1.5, hml_eligible_lines="Any", hml_mfg_lead_time_days=3)),
	"SA-CX-DRIVE": ("CX-200 Drive Assembly", IG_SUBASSY, "Nos", "84834000", 0, 0, "sa",
		dict(hml_machine_hours_per_unit=1, hml_eligible_lines="Any", hml_mfg_lead_time_days=2)),
	# Components (bought; also sold as components)
	"CMP-CYL-100": ("Hydraulic Cylinder 100 mm Bore", IG_COMPONENTS, "Nos", "84122100", 18000, 24500, "buysell",
		dict(lead_time_days=28, hml_criticality="A - Critical", hml_abc_class="A", supplier="hydrotech")),
	"CMP-PUMP-GP20": ("Gear Pump 20 LPM", IG_COMPONENTS, "Nos", "84136010", 12500, 16800, "buysell",
		dict(lead_time_days=21, hml_criticality="A - Critical", hml_abc_class="A", supplier="hydrotech")),
	"CMP-MOTOR-5HP": ("Electric Motor 5 HP 3-Phase", IG_COMPONENTS, "Nos", "85015210", 14000, 18900, "buysell",
		dict(lead_time_days=14, hml_criticality="B - Important", hml_abc_class="B", supplier="delhielec")),
	"CMP-MOTOR-2HP": ("Electric Motor 2 HP 3-Phase", IG_COMPONENTS, "Nos", "85015210", 7500, 10200, "buysell",
		dict(lead_time_days=14, hml_criticality="B - Important", hml_abc_class="B", supplier="delhielec")),
	"CMP-GEARBOX-30": ("Worm Gearbox 30:1", IG_COMPONENTS, "Nos", "84834000", 9800, 13200, "buysell",
		dict(lead_time_days=21, hml_criticality="B - Important", hml_abc_class="B", supplier="precision")),
	"CMP-PLC-24": ("PLC Controller 24 I/O", IG_COMPONENTS, "Nos", "85371000", 22000, 29500, "buysell",
		dict(lead_time_days=28, hml_criticality="A - Critical", hml_abc_class="A", supplier="delhielec")),
	"CMP-BRG-6205": ("Ball Bearing 6205-2RS", IG_COMPONENTS, "Nos", "84821020", 180, 260, "buysell",
		dict(lead_time_days=2, hml_criticality="C - Standard", hml_abc_class="C", supplier="precision")),
	"CMP-ROLLER-50": ("Conveyor Roller 50 mm x 600 mm", IG_COMPONENTS, "Nos", "84829900", 450, 640, "buysell",
		dict(lead_time_days=7, hml_criticality="C - Standard", hml_abc_class="B", supplier="precision")),
	"CMP-MANIFOLD-HX": ("HX-500 Custom Manifold Block", IG_COMPONENTS, "Nos", "84129090", 8600, 0, "buy",
		dict(lead_time_days=21, hml_criticality="A - Critical", hml_abc_class="A", supplier="abcsupplies")),
	# Raw materials
	"RM-MS-PLATE-10": ("MS Plate 10 mm IS2062", IG_RAW, "Kg", "72085190", 72, 0, "buy",
		dict(lead_time_days=28, hml_criticality="A - Critical", hml_abc_class="A", supplier="bharat")),
	"RM-MS-CHANNEL-100": ("MS Channel 100x50", IG_RAW, "Kg", "72163100", 68, 0, "buy",
		dict(lead_time_days=28, hml_criticality="B - Important", hml_abc_class="A", supplier="bharat")),
	"RM-PAINT-EPOXY": ("Epoxy Paint - RAL 5015 Blue", IG_RAW, "Litre", "32089090", 420, 0, "buy",
		dict(lead_time_days=5, hml_criticality="C - Standard", hml_abc_class="B", supplier="rapid")),
	"RM-WELD-E7018": ("Welding Electrode E7018 3.15 mm", IG_RAW, "Kg", "83112000", 210, 0, "buy",
		dict(lead_time_days=2, hml_criticality="C - Standard", hml_abc_class="C", supplier="bharat")),
	"RM-HYD-OIL-68": ("Hydraulic Oil ISO VG 68", IG_RAW, "Litre", "27101980", 160, 0, "buy",
		dict(lead_time_days=5, hml_criticality="B - Important", hml_abc_class="B", supplier="hydrotech", batch=1)),
	"RM-BELT-PVC-600": ("PVC Conveyor Belt 600 mm", IG_RAW, "Meter", "59100090", 1250, 0, "buy",
		dict(lead_time_days=14, hml_criticality="B - Important", hml_abc_class="B", supplier="rapid")),
	"RM-BOLT-M12": ("Hex Bolt M12 x 50 with Nut", IG_RAW, "Nos", "73181500", 12, 0, "buy",
		dict(lead_time_days=2, hml_criticality="C - Standard", hml_abc_class="C", supplier="shree")),
	# Spares (seasonal Q4 demand)
	"SP-SEAL-KIT-HX": ("HX-500 Cylinder Seal Kit", IG_SPARES, "Set", "40169320", 2200, 3500, "buysell",
		dict(lead_time_days=21, hml_criticality="B - Important", hml_abc_class="B", supplier="hydrotech",
			hml_demand_pattern="Seasonal - Q4 Spike")),
	"SP-FILTER-RET": ("Hydraulic Return Line Filter", IG_SPARES, "Nos", "84212300", 850, 1400, "buysell",
		dict(lead_time_days=7, hml_criticality="C - Standard", hml_abc_class="C", supplier="hydrotech",
			hml_demand_pattern="Seasonal - Q4 Spike")),
	"SP-BELT-600-10M": ("Replacement Belt 600 mm x 10 m", IG_SPARES, "Nos", "59100090", 11000, 16500, "buysell",
		dict(lead_time_days=14, hml_criticality="B - Important", hml_abc_class="B", supplier="rapid",
			hml_demand_pattern="Seasonal - Q4 Spike")),
	"SP-ROLLER-SET10": ("Conveyor Roller Set (10 pcs)", IG_SPARES, "Set", "84829900", 4300, 6500, "buysell",
		dict(lead_time_days=7, hml_criticality="C - Standard", hml_abc_class="C", supplier="precision",
			hml_demand_pattern="Seasonal - Q4 Spike")),
	"SP-HOSE-KIT": ("Hydraulic Hose Kit (4 hoses)", IG_SPARES, "Set", "40093100", 3100, 4800, "buysell",
		dict(lead_time_days=10, hml_criticality="C - Standard", hml_abc_class="C", supplier="hydrotech",
			hml_demand_pattern="Seasonal - Q4 Spike")),
}

INCOME_BY_GROUP = {
	IG_EQUIPMENT: acc("Sales - Equipment"),
	IG_SPARES: acc("Sales - Spares"),
	IG_COMPONENTS: acc("Sales - Components"),
}


def _ensure_hsn(code):
	if not frappe.db.exists("GST HSN Code", code):
		frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": code, "description": "Added by horizon_erp seed"}).insert(
			ignore_permissions=True
		)


def step_items():
	for code, (name, group, uom, hsn, buy_rate, sell_rate, kind, extra) in ITEMS.items():
		extra = dict(extra)
		supplier_key = extra.pop("supplier", None)
		batch = extra.pop("batch", 0)
		_ensure_hsn(hsn)
		if not frappe.db.exists("Item", code):
			default_wh = WH_FG if kind in ("fg", "buysell") and group != IG_COMPONENTS else WH_RM
			if kind == "sa":
				default_wh = WH_WIP
			defaults = {
				"company": COMPANY,
				"default_warehouse": default_wh,
				"default_price_list": "HML Standard Buying",
			}
			if group in CATEGORY_COST_CENTER:
				defaults["selling_cost_center"] = CATEGORY_COST_CENTER[group]
				defaults["buying_cost_center"] = CATEGORY_COST_CENTER[group]
			if group in INCOME_BY_GROUP:
				defaults["income_account"] = INCOME_BY_GROUP[group]
			if supplier_key:
				defaults["default_supplier"] = supplier_name(supplier_key)
			doc = frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": name,
					"description": name,
					"item_group": group,
					"stock_uom": uom,
					"gst_hsn_code": hsn,
					"is_stock_item": 1,
					"include_item_in_manufacturing": 1,
					"is_purchase_item": 1 if kind in ("buy", "buysell") else 0,
					"is_sales_item": 1 if kind in ("fg", "buysell") else 0,
					"has_batch_no": batch,
					"create_new_batch": 0,
					"has_expiry_date": 0,
					"valuation_rate": buy_rate or None,
					"standard_rate": 0,
					"item_defaults": [defaults],
					"inspection_required_before_purchase": 1 if kind in ("buy", "buysell") else 0,
					**extra,
				}
			)
			doc.insert(set_name=code, ignore_permissions=True)
			log(f"+ Item: {code}")
		if buy_rate:
			_price(code, "HML Standard Buying", buy_rate, uom)
		if sell_rate:
			_price(code, "HML Standard Selling", sell_rate, uom)
			# North region carries freight: +4 %
			_price(code, "HML North Region Selling", round(sell_rate * 1.04, -1), uom)


def _price(item_code, price_list, rate, uom):
	if not frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list}):
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"price_list_rate": rate,
				"uom": uom,
				"valid_from": OPENING_DATE,
			}
		).insert(ignore_permissions=True)


# ----------------------------------------------------- roles, users, permissions

# key: (first, last, roles, branch restriction, department)
USERS = {
	"rajesh.menon": ("Rajesh", "Menon", [ROLE_FD, "Accounts Manager", "Accounts User", "Purchase User", "Report Manager"], None),
	"priya.nair": ("Priya", "Nair", [ROLE_OPS, "Manufacturing Manager", "Manufacturing User", "Stock Manager", "Stock User", "Quality Manager"], None),
	"amit.kapoor": ("Amit", "Kapoor", [ROLE_SALES_DIR, "Sales Manager", "Sales User", "Sales Master Manager"], None),
	"neha.joshi": ("Neha", "Joshi", [ROLE_HR, "HR Manager", "HR User", "Leave Approver", "Projects Manager"], None),
	"vikram.rao": ("Vikram", "Rao", [ROLE_PROC, "Purchase Manager", "Purchase User", "Purchase Master Manager"], None),
	"suresh.patil": ("Suresh", "Patil", [ROLE_DEPT_HEAD, "Purchase User", "Manufacturing User", "Stock User", "Leave Approver"], None),
	"anil.deshmukh": ("Anil", "Deshmukh", [ROLE_WH_MGR, "Stock User", "Delivery User"], "mumbai"),
	"kavita.singh": ("Kavita", "Singh", [ROLE_WH_MGR, "Stock User", "Delivery User"], "delhi"),
	"ramesh.iyer": ("Ramesh", "Iyer", [ROLE_QI, "Quality Manager", "Stock User", "Manufacturing User"], None),
	"sanjay.verma": ("Sanjay", "Verma", [ROLE_SALES_MGR, "Sales Manager", "Sales User"], None),
	"rohan.mehta": ("Rohan", "Mehta", [ROLE_SALES_USER, "Sales User"], None),
}


def user_email(key):
	return f"{key}@{EMAIL_DOMAIN}"


def step_users():
	for key, (first, last, roles, _restrict) in USERS.items():
		email = user_email(key)
		if frappe.db.exists("User", email):
			continue
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first,
				"last_name": last,
				"send_welcome_email": 0,
				"user_type": "System User",
				"new_password": TEST_PASSWORD,
				"roles": [{"role": r} for r in roles],
			}
		)
		user.insert(ignore_permissions=True)
		log(f"+ User: {email}")


def _user_permission(user, allow, value, **kw):
	if frappe.db.exists("User Permission", {"user": user, "allow": allow, "for_value": value}):
		return
	frappe.get_doc(
		{"doctype": "User Permission", "user": user, "allow": allow, "for_value": value, "apply_to_all_doctypes": 1, **kw}
	).insert(ignore_permissions=True)
	log(f"+ User Permission: {user} {allow}={value}")


def step_user_permissions():
	"""HML users see only HML; warehouse managers see only their location.

	Finance (Rajesh) and Operations (Priya) get Company only, so they see both
	locations and every warehouse.
	"""
	for key, (_f, _l, _roles, restrict) in USERS.items():
		email = user_email(key)
		_user_permission(email, "Company", COMPANY, is_default=1)
		if restrict == "mumbai":
			_user_permission(email, "Warehouse", WH_MUMBAI, is_default=0)
			_user_permission(email, "Branch", BRANCH_MUMBAI, is_default=1)
		elif restrict == "delhi":
			_user_permission(email, "Warehouse", WH_DELHI, is_default=0)
			_user_permission(email, "Branch", BRANCH_DELHI, is_default=1)


# --------------------------------------------------------------- opening stock

OPENING_STOCK = [
	# (warehouse, item, qty)
	(WH_RM, "RM-MS-PLATE-10", 4200),
	(WH_RM, "RM-MS-CHANNEL-100", 3100),
	(WH_RM, "RM-PAINT-EPOXY", 160),
	(WH_RM, "RM-WELD-E7018", 140),
	(WH_RM, "RM-BELT-PVC-600", 90),
	(WH_RM, "RM-BOLT-M12", 2600),
	(WH_RM, "CMP-CYL-100", 6),
	(WH_RM, "CMP-PUMP-GP20", 5),
	(WH_RM, "CMP-MOTOR-5HP", 8),
	(WH_RM, "CMP-MOTOR-2HP", 14),
	(WH_RM, "CMP-GEARBOX-30", 9),
	(WH_RM, "CMP-PLC-24", 4),
	(WH_RM, "CMP-BRG-6205", 420),
	(WH_RM, "CMP-ROLLER-50", 260),
	(WH_RM, "CMP-MANIFOLD-HX", 3),
	(WH_FG, "SP-SEAL-KIT-HX", 40),
	(WH_FG, "SP-FILTER-RET", 75),
	(WH_FG, "SP-BELT-600-10M", 12),
	(WH_FG, "SP-ROLLER-SET10", 30),
	(WH_FG, "SP-HOSE-KIT", 25),
	(WH_DELHI_FG, "SP-SEAL-KIT-HX", 15),
	(WH_DELHI_FG, "SP-FILTER-RET", 30),
	(WH_DELHI_FG, "SP-ROLLER-SET10", 10),
	(WH_DELHI_FG, "CMP-MOTOR-2HP", 6),
	(WH_DELHI_FG, "CMP-BRG-6205", 150),
]


def step_opening_stock():
	if frappe.db.exists("Stock Reconciliation", {"company": COMPANY, "purpose": "Opening Stock", "docstatus": 1}):
		log("opening stock exists")
		return
	doc = frappe.get_doc(
		{
			"doctype": "Stock Reconciliation",
			"company": COMPANY,
			"purpose": "Opening Stock",
			"expense_account": acc("Temporary Opening"),
			"cost_center": cc("Admin"),
			"items": [],
		}
	)
	set_posting(doc, OPENING_DATE, "08:00:00")
	for warehouse, item, qty in OPENING_STOCK:
		rate = frappe.db.get_value("Item", item, "valuation_rate")
		doc.append("items", {"item_code": item, "warehouse": warehouse, "qty": qty, "valuation_rate": rate})
	doc.insert(ignore_permissions=True)
	doc.submit()
	log(f"+ Opening Stock Reconciliation {doc.name} ({len(doc.items)} rows)")
	frappe.db.set_value(
		"Item",
		{"name": ("in", [r[1] for r in OPENING_STOCK])},
		"hml_last_counted_on",
		OPENING_DATE,
		update_modified=False,
	)


# --------------------------------------------------------- recurring journals

RECURRING = [
	# (title, expense account, amount, cost center, branch)
	("Factory rent - Mumbai HQ", acc("Factory Rent"), 350000, cc("Mfg - Equipment"), BRANCH_MUMBAI),
	("Warehouse rent - Delhi DC", acc("Warehouse Rent"), 120000, cc("Sales"), BRANCH_DELHI),
	("Electricity - Mumbai plant", acc("Factory Power and Fuel"), 210000, cc("Mfg - Equipment"), BRANCH_MUMBAI),
	("Office utilities - Mumbai", acc("Utility Expenses"), 45000, cc("Admin"), BRANCH_MUMBAI),
]


def step_recurring_journals():
	"""Monthly rent/utility JEs Apr-Nov 2026 + Auto Repeat from December.

	Cost center and Location come from the template row, so the recurring
	copies Auto Repeat creates carry them automatically.
	"""
	bank = acc("HDFC Bank - Current Account")
	last = None
	for i in range(8):  # Apr .. Nov 2026
		month_end = get_last_day(add_months(OPENING_DATE, i))
		for title, account, amount, cost_center, branch in RECURRING:
			remark = f"{title} - {getdate(month_end).strftime('%b %Y')}"
			if frappe.db.exists("Journal Entry", {"company": COMPANY, "user_remark": remark, "docstatus": 1}):
				continue
			je = frappe.get_doc(
				{
					"doctype": "Journal Entry",
					"company": COMPANY,
					"voucher_type": "Journal Entry",
					"posting_date": month_end,
					"user_remark": remark,
					"title": title,
					"accounts": [
						{
							"account": account,
							"debit_in_account_currency": amount,
							"cost_center": cost_center,
							"branch": branch,
						},
						{
							"account": bank,
							"credit_in_account_currency": amount,
							"cost_center": cost_center,
							"branch": branch,
						},
					],
					"cheque_no": f"NEFT-{getdate(month_end).strftime('%y%m')}-{zlib.crc32(title.encode()) % 1000:03d}",
					"cheque_date": month_end,
				}
			)
			je.insert(ignore_permissions=True)
			je.submit()
			last = je
	if last:
		log(f"+ recurring journals posted up to {last.posting_date}")

	for title, *_ in RECURRING:
		template = frappe.db.get_value(
			"Journal Entry",
			{"company": COMPANY, "title": title, "docstatus": 1},
			"name",
			order_by="posting_date desc",
		)
		if not template or frappe.db.exists("Auto Repeat", {"reference_document": template}):
			continue
		frappe.db.set_value("Journal Entry", template, "auto_repeat", None)
		ar = frappe.get_doc(
			{
				"doctype": "Auto Repeat",
				"reference_doctype": "Journal Entry",
				"reference_document": template,
				"frequency": "Monthly",
				"start_date": "2026-12-31",
				"repeat_on_last_day": 1,
				"submit_on_creation": 0,
				"notify_by_email": 0,
			}
		)
		ar.insert(ignore_permissions=True)
		log(f"+ Auto Repeat {ar.name} for {title}")


STEPS = [
	("company", step_company),
	("gst_registrations", step_gst_registrations),
	("location_dimension", step_location_dimension),
	("cost_centers", step_cost_centers),
	("accounts", step_accounts),
	("warehouses", step_warehouses),
	("groups", step_groups),
	("price_lists", step_price_lists),
	("customers", step_customers),
	("suppliers", step_suppliers),
	("internal_parties", step_internal_parties),
	("items", step_items),
	("users", step_users),
	("user_permissions", step_user_permissions),
	("opening_stock", step_opening_stock),
	("recurring_journals", step_recurring_journals),
]
