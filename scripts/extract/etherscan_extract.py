"""Extract raw on-chain activity from Etherscan and save timestamped JSON files.

The extractor pulls normal transactions and ERC-20 token transfers. It does not
clean or analyze the responses; later pipeline stages can process the immutable
raw files for auditability and reproducibility.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from readme_progress import record_progress

load_dotenv(PROJECT_ROOT / ".env")

ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"
DEFAULT_CHAIN_ID = 1
DEFAULT_CONTRACT_ADDRESS = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
REQUEST_DELAY_SECONDS = 0.25
PAGE_SIZE = 1000
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "etherscan"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_api_key() -> str:
    """Read the Etherscan API key and fail clearly when it is missing."""
    api_key = os.environ.get("ETHERSCAN_API_KEY")
    if not api_key:
        logger.error("ETHERSCAN_API_KEY is not set. Add it to .env.")
        sys.exit(1)
    return api_key


def fetch_paginated(action: str, address: str, api_key: str, chain_id: int, max_pages: int) -> list[dict]:
    """Fetch paginated raw records for an Etherscan account action."""
    all_records: list[dict] = []

    for page in range(1, max_pages + 1):
        params = {
            "chainid": chain_id,
            "module": "account",
            "action": action,
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "page": page,
            "offset": PAGE_SIZE,
            "sort": "desc",
            "apikey": api_key,
        }
        logger.info("Fetching %s page %s for %s...", action, page, address)

        try:
            response = requests.get(ETHERSCAN_BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, json.JSONDecodeError) as error:
            logger.error("Request failed on page %s: %s", page, error)
            break

        status = payload.get("status")
        message = payload.get("message", "")
        result = payload.get("result")
        if status == "0":
            if "No transactions found" in message or "No records found" in message:
                logger.info("No more %s results at page %s.", action, page)
            else:
                logger.error("Etherscan API error on page %s: %s - %s", page, message, result)
            break
        if not isinstance(result, list):
            logger.error("Unexpected result format on page %s: %s", page, result)
            break
        if not result:
            break

        all_records.extend(result)
        logger.info("  -> %s records (running total: %s)", len(result), len(all_records))
        if len(result) < PAGE_SIZE:
            break
        time.sleep(REQUEST_DELAY_SECONDS)

    return all_records


def save_raw(records: list[dict], dataset_name: str, address: str, chain_id: int) -> Path:
    """Save records in a timestamped envelope without overwriting prior extracts."""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{dataset_name}_{chain_id}_{address.lower()}_{timestamp}.json"
    filepath = RAW_DATA_DIR / filename
    output = {
        "extracted_at_utc": timestamp,
        "source": "etherscan",
        "chain_id": chain_id,
        "dataset": dataset_name,
        "address": address,
        "record_count": len(records),
        "records": records,
    }
    filepath.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Saved %s records to %s", len(records), filepath)
    return filepath


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract raw transaction and ERC-20 transfer data from Etherscan."
    )
    parser.add_argument("--address", default=DEFAULT_CONTRACT_ADDRESS)
    parser.add_argument("--chain-id", type=int, default=int(os.getenv("ETHERSCAN_CHAIN_ID", DEFAULT_CHAIN_ID)))
    parser.add_argument("--max-pages", type=int, default=3, help="Maximum pages per dataset.")
    args = parser.parse_args()
    if args.max_pages < 1:
        parser.error("--max-pages must be at least 1")

    api_key = get_api_key()
    logger.info("Starting extraction for chain %s and address %s", args.chain_id, args.address)

    extracted_counts = {}
    for dataset_name in ("txlist", "tokentx"):
        records = fetch_paginated(dataset_name, args.address, api_key, args.chain_id, args.max_pages)
        extracted_counts[dataset_name] = len(records)
        if records:
            save_raw(records, dataset_name, args.address, args.chain_id)
        if dataset_name == "txlist":
            time.sleep(REQUEST_DELAY_SECONDS)

    record_progress(
        "Raw extraction",
        [
            f"Extracted {extracted_counts['txlist']} normal transactions.",
            f"Extracted {extracted_counts['tokentx']} ERC-20 token transfers.",
            f"Saved raw JSON output to `{RAW_DATA_DIR.relative_to(PROJECT_ROOT)}/`.",
        ],
        f"{sum(extracted_counts.values())} records fetched across both datasets.",
        "Run `python scripts/staging/build_sqlite.py`.",
    )
    logger.info("Extraction complete. Raw files are in %s", RAW_DATA_DIR)


if __name__ == "__main__":
    main()
