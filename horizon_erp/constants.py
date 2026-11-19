"""Single source of truth for Horizon Manufacturing Ltd names.

Every HML-specific rule in this app is gated on COMPANY, so the other company
on the site (Leelas) keeps stock ERPNext behaviour.
"""

COMPANY = "Horizon Manufacturing Ltd"
ABBR = "HML"
COMPANY_ID = "2"  # agrica_dms naming patch puts this into `.CI.` series parts

# GSTINs: the assignment's Mumbai GSTIN 27AABCU9602H1Z0 fails the GSTIN
# check-digit test, so the valid check digit is used (see decision log D-04).
PAN = "AABCU9602H"
GSTIN_MUMBAI = "27AABCU9602H1Z9"
GSTIN_DELHI = "07AABCU9602H1ZB"

ADDRESS_MUMBAI = "HML Mumbai HQ-Billing"
ADDRESS_DELHI = "HML Delhi DC-Billing"

# Location accounting dimension (document type: Branch)
BRANCH_MUMBAI = "HQ Mumbai"
BRANCH_DELHI = "DC Delhi"


def wh(name):
	"""Warehouse full name, e.g. wh('Mumbai - Raw Materials')."""
	return f"{name} - {ABBR}"


def cc(name):
	"""Cost center full name, e.g. cc('Sales')."""
	return f"{name} - {ABBR}"


def acc(name):
	"""Account full name, e.g. acc('Rent Expense')."""
	return f"{name} - {ABBR}"


WH_ROOT = wh("All Warehouses")
WH_MUMBAI = wh("Mumbai HQ")
WH_DELHI = wh("Delhi DC")
WH_RM = wh("Mumbai - Raw Materials")
WH_FG = wh("Mumbai - Finished Goods")
WH_WIP = wh("Mumbai - WIP")
WH_QC = wh("Mumbai - QC Hold")
WH_REJECTED = wh("Mumbai - Rejected")
WH_SCRAP = wh("Mumbai - Scrap")
WH_DELHI_FG = wh("Delhi - Finished Goods")
WH_TRANSIT = wh("Goods In Transit")

# Item groups (= product categories)
IG_EQUIPMENT = "Equipment"
IG_SPARES = "Spares"
IG_COMPONENTS = "Components"
IG_RAW = "HML Raw Materials"
IG_SUBASSY = "HML Sub-Assemblies"

CATEGORY_COST_CENTER = {
	IG_EQUIPMENT: cc("Mfg - Equipment"),
	IG_SPARES: cc("Mfg - Spares"),
	IG_COMPONENTS: cc("Mfg - Components"),
}

# Roles (global on the site, so prefixed)
ROLE_FD = "HML Finance Director"
ROLE_OPS = "HML Operations Head"
ROLE_SALES_DIR = "HML Sales Director"
ROLE_HR = "HML HR Manager"
ROLE_PROC = "HML Procurement Manager"
ROLE_DEPT_HEAD = "HML Department Head"
ROLE_WH_MGR = "HML Warehouse Manager"
ROLE_QI = "HML Quality Inspector"
ROLE_SALES_MGR = "HML Sales Manager"
ROLE_SALES_USER = "HML Sales Executive"

HML_ROLES = [
	ROLE_FD,
	ROLE_OPS,
	ROLE_SALES_DIR,
	ROLE_HR,
	ROLE_PROC,
	ROLE_DEPT_HEAD,
	ROLE_WH_MGR,
	ROLE_QI,
	ROLE_SALES_MGR,
	ROLE_SALES_USER,
]


def is_hml(doc_or_company):
	"""True when a document (or company name) belongs to Horizon."""
	if isinstance(doc_or_company, str):
		return doc_or_company == COMPANY
	return getattr(doc_or_company, "company", None) == COMPANY
