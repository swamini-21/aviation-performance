"""
Bulk-download BTS Reporting Carrier On-Time Performance monthly zip files.

Run this LOCALLY on your own machine (not in a Databricks notebook) --
Databricks Free Edition's serverless egress is allowlisted and will not
reliably reach transtats.bts.gov.

After this finishes, unzip the files and upload the CSVs to your Databricks
UC Volume (airline_analytics.bronze.landing) -- either by dragging them into
the Catalog UI, or via the Databricks CLI for a bigger batch (see note at
the bottom of this file).
"""

import requests
import time
from pathlib import Path

# -----------------------------------------------------------------------
# CONFIG -- adjust as needed
# -----------------------------------------------------------------------
START_YEAR = 2018
END_YEAR = 2018         # BTS has ~3 month reporting lag, so recent months
                          # in the current year may 404 -- that's expected,
                          # the script just skips them.
OUTPUT_DIR = Path("bts_ontime_raw")
BASE_URL = "https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
DELAY_BETWEEN_REQUESTS_SEC = 2   # be a polite citizen on a .gov server
TIMEOUT_SEC = 120                # these files can be 20-30MB+, allow time
MAX_RETRIES = 3

# -----------------------------------------------------------------------

def download_month(year: int, month: int, out_dir: Path) -> str:
    """Download one month's zip. Returns 'ok', 'skipped', 'not_found', or 'failed'."""
    url = BASE_URL.format(year=year, month=month)
    dest = out_dir / f"on_time_{year}_{month:02d}.zip"

    if dest.exists() and dest.stat().st_size > 0:
        return "skipped"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, stream=True, timeout=TIMEOUT_SEC)
            if resp.status_code == 404:
                return "not_found"
            resp.raise_for_status()

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
            return "ok"

        except requests.exceptions.RequestException as e:
            print(f"  attempt {attempt}/{MAX_RETRIES} failed for {year}-{month:02d}: {e}")
            if dest.exists():
                dest.unlink()  # remove partial file
            time.sleep(3)

    return "failed"


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    results = {"ok": [], "skipped": [], "not_found": [], "failed": []}

    for year in range(START_YEAR, END_YEAR + 1):
        for month in range(1, 3):
            print(f"Fetching {year}-{month:02d}...", end=" ")
            status = download_month(year, month, OUTPUT_DIR)
            print(status)
            results[status].append(f"{year}-{month:02d}")
            time.sleep(DELAY_BETWEEN_REQUESTS_SEC)

    print("\n===== SUMMARY =====")
    for status, months in results.items():
        print(f"{status}: {len(months)}")
    if results["not_found"]:
        print(f"\nNot found (expected for months not yet published): {results['not_found']}")
    if results["failed"]:
        print(f"\nFAILED (worth retrying manually): {results['failed']}")


if __name__ == "__main__":
    main()

# -----------------------------------------------------------------------
# AFTER DOWNLOADING:
#
# 1. Unzip everything, e.g.:
#      cd bts_ontime_raw && for f in *.zip; do unzip -o "$f" -d unzipped/; done
#
# 2. Upload to your Databricks UC Volume. For ~200 files, the Databricks CLI
#    is much faster than drag-and-drop in the browser:
#      pip install databricks-cli
#      databricks configure --token   # needs your workspace URL + a personal access token
#      databricks fs cp -r ./unzipped dbfs:/Volumes/airline_analytics/bronze/landing/
#
#    (If you'd rather stick with drag-and-drop in the Catalog UI, that works
#    fine too, just slower for this many files -- batches of 20-30 at a time.)
# -----------------------------------------------------------------------
