#!/usr/bin/env python3
"""Audit ClientCellar supplier link configuration.

By default this validates local supplier configuration only. Use --check-live
when you want to make network requests to supplier websites.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.supplier_links import SUPPLIER_LINK_CONFIG, validate_supplier_links  # noqa: E402


def live_status(url: str, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "ClientCellar link audit"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return str(response.status)
    except urllib.error.HTTPError as error:
        if error.code in {403, 405}:
            fallback = urllib.request.Request(
                url,
                method="GET",
                headers={"User-Agent": "ClientCellar link audit"},
            )
            try:
                with urllib.request.urlopen(fallback, timeout=timeout) as response:
                    return str(response.status)
            except Exception as fallback_error:  # noqa: BLE001
                return f"{error.code}; GET failed: {fallback_error.__class__.__name__}"
        return str(error.code)
    except Exception as error:  # noqa: BLE001
        return f"error: {error.__class__.__name__}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ClientCellar supplier links.")
    parser.add_argument("--check-live", action="store_true", help="Make live HEAD/GET requests to supplier URLs.")
    parser.add_argument("--timeout", type=int, default=8, help="Network timeout in seconds for live checks.")
    args = parser.parse_args()

    warnings = validate_supplier_links()
    if warnings:
        print("Malformed local supplier URLs:")
        for warning in warnings:
            print(f"- {warning}")
        return 1

    print("| Supplier | Active | Destination | Affiliate | Live status |")
    print("| --- | --- | --- | --- | --- |")
    for supplier_id, link in sorted(SUPPLIER_LINK_CONFIG.items()):
        url = link.url
        status = "not checked"
        if args.check_live and url:
            status = live_status(url, args.timeout)
        destination = url or "none"
        print(f"| {link.name} (`{supplier_id}`) | {link.active} | {destination} | {link.is_affiliate} | {status} |")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
