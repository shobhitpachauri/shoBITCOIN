"""
inspect_duplicates.py

Diagnostic, one-off script: finds raw tokentx records that collide on our
current dedupe key and prints them side by side. This does not modify the
database or raw files.

Usage:
    python scripts/staging/inspect_duplicates.py
"""

import json
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "etherscan"


def main() -> None:
    token_files = sorted(RAW_DATA_DIR.glob("tokentx_*.json"))
    if not token_files:
        print(f"No tokentx JSON files found in {RAW_DATA_DIR.resolve()}")
        return

    groups = defaultdict(list)
    for filepath in token_files:
        with filepath.open(encoding="utf-8") as file:
            payload = json.load(file)
        for record in payload.get("records", []):
            key = (
                record.get("hash"),
                record.get("contractAddress"),
                record.get("from"),
                record.get("to"),
                record.get("value"),
            )
            groups[key].append((filepath.name, record))

    colliding = {key: entries for key, entries in groups.items() if len(entries) > 1}
    if not colliding:
        print(
            "No colliding records found across raw files. The skipped row must "
            "have come from a different cause (re-run overlap between separate "
            "extraction runs) — check if you ran the extractor more than once."
        )
        return

    print(f"Found {len(colliding)} tx_hash+value combination(s) with multiple raw records:\n")
    for key, entries in colliding.items():
        tx_hash, contract, from_address, to_address, value = key
        print(f"tx_hash: {tx_hash}")
        print(f"  token_contract: {contract}")
        print(f"  from: {from_address}  ->  to: {to_address}")
        print(f"  value (raw units): {value}")
        print(f"  appears {len(entries)} times, in:")
        for filename, record in entries:
            print(f"    - file: {filename}")
            print(f"      full record: {json.dumps(record)}")
        print()


if __name__ == "__main__":
    main()
