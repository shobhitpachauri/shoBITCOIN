"""
build_sqlite.py

Staging step of the pipeline: reads raw JSON files produced by
etherscan_extract.py, cleans and types the data, and loads it into a
SQLite database with two tables: `transactions` and `token_transfers`.

This script is safe to re-run. It uses INSERT OR IGNORE with a primary/
unique key so re-running it after a fresh extraction will not create
duplicate rows.

Usage:
    python scripts/staging/build_sqlite.py

Input:  data/raw/etherscan/*.json   (written by etherscan_extract.py)
Output: data/staging/shobitcoin.db  (SQLite database)
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from readme_progress import record_progress

RAW_DATA_DIR = Path("data/raw/etherscan")
STAGING_DB_PATH = Path("data/staging/shobitcoin.db")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


CREATE_TRANSACTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS transactions (
    tx_hash          TEXT PRIMARY KEY,
    block_number     INTEGER,
    timestamp        TEXT,
    from_address     TEXT,
    to_address       TEXT,
    value_eth        REAL,
    gas_used         INTEGER,
    gas_price_gwei   REAL,
    is_error         INTEGER,
    method_id        TEXT,
    function_name    TEXT,
    source_contract  TEXT,
    loaded_at        TEXT
);
"""

CREATE_TOKEN_TRANSFERS_TABLE = """
CREATE TABLE IF NOT EXISTS token_transfers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_hash          TEXT,
    block_number     INTEGER,
    timestamp        TEXT,
    from_address     TEXT,
    to_address       TEXT,
    token_contract   TEXT,
    token_name       TEXT,
    token_symbol     TEXT,
    token_decimals   INTEGER,
    value_token      REAL,
    source_contract  TEXT,
    loaded_at        TEXT,
    UNIQUE (tx_hash, token_contract, from_address, to_address, value_token)
);
"""


def get_connection() -> sqlite3.Connection:
    STAGING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(STAGING_DB_PATH)
    conn.execute(CREATE_TRANSACTIONS_TABLE)
    conn.execute(CREATE_TOKEN_TRANSFERS_TABLE)
    conn.commit()
    return conn


def unix_to_iso(unix_ts: str) -> str | None:
    """Convert a Unix timestamp string to an ISO 8601 UTC string."""
    try:
        return datetime.fromtimestamp(int(unix_ts), tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def wei_to_eth(value_wei: str) -> float | None:
    try:
        return int(value_wei) / 1e18
    except (ValueError, TypeError):
        return None


def wei_to_gwei(value_wei: str) -> float | None:
    try:
        return int(value_wei) / 1e9
    except (ValueError, TypeError):
        return None


def token_value_to_human(value_raw: str, decimals: str) -> float | None:
    try:
        return int(value_raw) / (10 ** int(decimals))
    except (ValueError, TypeError, OverflowError):
        return None


def load_transactions(conn: sqlite3.Connection, filepath: Path) -> int:
    with filepath.open(encoding="utf-8") as file:
        payload = json.load(file)

    source_contract = payload.get("address")
    records = payload.get("records", [])
    loaded_at = datetime.now(timezone.utc).isoformat()
    rows = []

    for record in records:
        rows.append(
            (
                record.get("hash"),
                int(record["blockNumber"]) if record.get("blockNumber") else None,
                unix_to_iso(record.get("timeStamp")),
                record.get("from"),
                record.get("to"),
                wei_to_eth(record.get("value")),
                int(record["gasUsed"]) if record.get("gasUsed") else None,
                wei_to_gwei(record.get("gasPrice")),
                int(record.get("isError", 0) or 0),
                record.get("methodId"),
                record.get("functionName"),
                source_contract,
                loaded_at,
            )
        )

    cursor = conn.executemany(
        """
        INSERT OR IGNORE INTO transactions
        (tx_hash, block_number, timestamp, from_address, to_address,
         value_eth, gas_used, gas_price_gwei, is_error, method_id,
         function_name, source_contract, loaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return cursor.rowcount


def load_token_transfers(conn: sqlite3.Connection, filepath: Path) -> int:
    with filepath.open(encoding="utf-8") as file:
        payload = json.load(file)

    source_contract = payload.get("address")
    records = payload.get("records", [])
    loaded_at = datetime.now(timezone.utc).isoformat()
    rows = []

    for record in records:
        decimals = record.get("tokenDecimal")
        rows.append(
            (
                record.get("hash"),
                int(record["blockNumber"]) if record.get("blockNumber") else None,
                unix_to_iso(record.get("timeStamp")),
                record.get("from"),
                record.get("to"),
                record.get("contractAddress"),
                record.get("tokenName"),
                record.get("tokenSymbol"),
                int(decimals) if decimals else None,
                token_value_to_human(record.get("value"), decimals),
                source_contract,
                loaded_at,
            )
        )

    cursor = conn.executemany(
        """
        INSERT OR IGNORE INTO token_transfers
        (tx_hash, block_number, timestamp, from_address, to_address,
         token_contract, token_name, token_symbol, token_decimals,
         value_token, source_contract, loaded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return cursor.rowcount


def main() -> None:
    if not RAW_DATA_DIR.exists():
        logger.error("Raw data directory not found: %s", RAW_DATA_DIR.resolve())
        logger.error("Run scripts/extract/etherscan_extract.py first.")
        return

    conn = get_connection()
    tx_files = sorted(RAW_DATA_DIR.glob("txlist_*.json"))
    token_files = sorted(RAW_DATA_DIR.glob("tokentx_*.json"))

    if not tx_files and not token_files:
        logger.warning("No raw JSON files found in %s", RAW_DATA_DIR.resolve())

    total_tx_inserted = 0
    for filepath in tx_files:
        logger.info("Loading transactions from %s...", filepath.name)
        inserted = load_transactions(conn, filepath)
        logger.info("  -> %s new rows inserted (duplicates skipped)", inserted)
        total_tx_inserted += inserted

    total_token_inserted = 0
    for filepath in token_files:
        logger.info("Loading token transfers from %s...", filepath.name)
        inserted = load_token_transfers(conn, filepath)
        logger.info("  -> %s new rows inserted (duplicates skipped)", inserted)
        total_token_inserted += inserted

    tx_total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    token_total = conn.execute("SELECT COUNT(*) FROM token_transfers").fetchone()[0]
    conn.close()

    logger.info("Staging complete.")
    logger.info(
        "New rows this run: %s transactions, %s token transfers",
        total_tx_inserted,
        total_token_inserted,
    )
    logger.info(
        "Total rows in database: %s transactions, %s token transfers",
        tx_total,
        token_total,
    )
    logger.info("Database location: %s", STAGING_DB_PATH.resolve())
    record_progress(
        "SQLite staging",
        [
            "Loaded and typed raw transaction and token-transfer JSON.",
            "Applied duplicate protection with primary and unique keys.",
            "Created `data/staging/shobitcoin.db`.",
        ],
        f"{tx_total} transactions and {token_total} unique token transfers in SQLite; {total_tx_inserted} and {total_token_inserted} new rows this run.",
        "Run `python scripts/analytics/build_analytics.py`.",
    )


if __name__ == "__main__":
    main()
