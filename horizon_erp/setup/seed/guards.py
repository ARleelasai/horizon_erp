"""Process-local guards used only while seeding.

* external_calls_blocked(): any outbound HTTP made through `requests` to a
  non-local host gets a fake 503 response. Other apps on this site call
  DataHub, a Neo4j microservice and the GST API from their hooks; they all
  swallow errors, so a 503 keeps them quiet without touching site settings.
* original_tax_setup(): agrica_dms monkey-patches ERPNext's
  `taxes_setup.from_detailed_data`. The patched version skips GST accounts and
  Sales/Purchase tax templates, and commits mid-transaction. For HML we want
  the stock India Compliance behaviour, so the original function is restored
  for the duration of company creation.
  HRMS's India regional setup (run on every new India company) re-syncs global
  custom fields and issues ALTER TABLE; inside a transaction that raises
  ImplicitCommitError. Those fields already exist on this site, so the call is
  skipped during company creation (salary component fixtures still run).
"""

import contextlib
import importlib.util
from urllib.parse import urlparse

import requests

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "fsm.local"}
BLOCKED = []


def _fake_response(url):
	resp = requests.Response()
	resp.status_code = 503
	resp._content = b'{"message": "blocked by horizon_erp seed"}'
	resp.url = url
	resp.headers["Content-Type"] = "application/json"
	return resp


@contextlib.contextmanager
def external_calls_blocked():
	original = requests.sessions.Session.request

	def guarded(self, method, url, *args, **kwargs):
		host = (urlparse(url).hostname or "").lower()
		if host in LOCAL_HOSTS:
			return original(self, method, url, *args, **kwargs)
		BLOCKED.append(f"{method} {host}")
		return _fake_response(url)

	requests.sessions.Session.request = guarded
	try:
		yield
	finally:
		requests.sessions.Session.request = original
		if BLOCKED:
			hosts = sorted(set(BLOCKED))
			print(f"  [guard] blocked {len(BLOCKED)} outbound call(s): {', '.join(hosts)}")
			BLOCKED.clear()


def _load_original_taxes_setup():
	import erpnext.setup.setup_wizard.operations.taxes_setup as patched

	spec = importlib.util.spec_from_file_location("hml_original_taxes_setup", patched.__file__)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return patched, module.from_detailed_data


@contextlib.contextmanager
def original_tax_setup():
	import hrms.overrides.company as hrms_company
	import india_compliance.gst_india.overrides.company as ic_company

	patched_module, original = _load_original_taxes_setup()
	saved_patched = patched_module.from_detailed_data
	saved_ic = ic_company.from_detailed_data
	saved_regional = hrms_company.run_regional_setup
	patched_module.from_detailed_data = original
	ic_company.from_detailed_data = original
	hrms_company.run_regional_setup = lambda country: None
	try:
		yield
	finally:
		hrms_company.run_regional_setup = saved_regional
		patched_module.from_detailed_data = saved_patched
		ic_company.from_detailed_data = saved_ic
