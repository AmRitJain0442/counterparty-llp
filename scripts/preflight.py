"""Free account preflight. Reads credentials from the environment and prints entitlements."""
import os

import requests

from backend.providers import OPERATIONS


def main():
    key = os.getenv("CRUSTDATA_API_KEY")
    if not key:
        raise SystemExit("Set CRUSTDATA_API_KEY for this process.")
    headers = {"Authorization": f"Bearer {key}", "x-api-version": "2025-11-01"}
    base = "https://api.crustdata.com/account/"
    with requests.Session() as session:
        prices = session.get(base + "endpoints", headers=headers, timeout=20)
        prices.raise_for_status()
        balance = session.get(base + "credits", headers=headers, timeout=20)
        balance.raise_for_status()
    print(f"Available credits: {balance.json()['account']['credits']}")
    entitled = {row["path"]: row for row in prices.json()["endpoints"]}
    for path in OPERATIONS.values():
        row = entitled.get(path, {})
        print(f"{path:24} {row.get('status', 'not listed'):12} "
              f"base={row.get('base_credits', '?')} rpm={row.get('effective_rate_limit_rpm', '?')}")


if __name__ == "__main__":
    main()
