#!/usr/bin/env python3
"""Delhi DC client for the HQ inventory snapshot API, with retries.

Run every 4 hours from cron on the Delhi side:
	0 */4 * * *  python3 retry_client.py --url https://erp.horizon.example --warehouse "Delhi DC"
Credentials come from the HML_API_KEY / HML_API_SECRET environment variables.

Retry policy (assignment): up to 3 retries with backoff 1 s, 5 s, 25 s on
network errors, HTTP 5xx and 429 (honouring retry_after_seconds when it is
shorter than the schedule). 4xx client errors are not retried. Every attempt
is logged to stdout / the log file.
"""

import argparse
import json
import logging
import os
import sys
import time

import requests

BACKOFF = [1, 5, 25]
log = logging.getLogger("hml-inventory-client")


def fetch_snapshot(base_url, warehouse, critical_only=False, session=None, sleep=time.sleep):
	session = session or requests.Session()
	url = f"{base_url.rstrip('/')}/api/method/get_inventory_snapshot"
	headers = {"Authorization": f"token {os.environ['HML_API_KEY']}:{os.environ['HML_API_SECRET']}"}
	payload = {"warehouse": warehouse, "filter_by_criticality": critical_only}
	attempts = len(BACKOFF) + 1
	for attempt in range(1, attempts + 1):
		try:
			resp = session.post(url, json=payload, headers=headers, timeout=30)
			if resp.status_code == 200:
				data = resp.json().get("message", {})
				log.info("attempt %s ok: %s items, %s alerts", attempt, len(data.get("items", [])), len(data.get("low_stock_alerts", [])))
				return data
			retryable = resp.status_code == 429 or resp.status_code >= 500
			log.warning("attempt %s failed: HTTP %s %s", attempt, resp.status_code, resp.text[:200])
			if not retryable:
				raise RuntimeError(f"non-retryable HTTP {resp.status_code}")
			wait = BACKOFF[attempt - 1] if attempt <= len(BACKOFF) else None
		except requests.RequestException as e:
			log.warning("attempt %s network error: %s", attempt, e)
			wait = BACKOFF[attempt - 1] if attempt <= len(BACKOFF) else None
		if wait is None:
			break
		log.info("retrying in %s s", wait)
		sleep(wait)
	raise RuntimeError(f"inventory snapshot failed after {attempts} attempts")


def main():
	p = argparse.ArgumentParser()
	p.add_argument("--url", required=True)
	p.add_argument("--warehouse", default="Delhi DC")
	p.add_argument("--critical-only", action="store_true")
	p.add_argument("--out", help="write JSON snapshot to this file")
	args = p.parse_args()
	logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
	data = fetch_snapshot(args.url, args.warehouse, args.critical_only)
	text = json.dumps(data, indent=2)
	if args.out:
		open(args.out, "w").write(text)
	else:
		sys.stdout.write(text + "\n")


if __name__ == "__main__":
	main()
