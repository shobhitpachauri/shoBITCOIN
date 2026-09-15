"""
build_analytics.py

Analytical layer of the pipeline. Builds SQL views on top of the staging
tables (transactions, token_transfers) and exports each view's current
results to CSV, ready for Power BI to import directly.

This script does not modify transactions/token_transfers; it only reads from
them and creates views plus CSV exports. It is safe to re-run after new data
is staged.

Usage:
    python scripts/analytics/build_analytics.py

Input:  data/staging/shobitcoin.db  (transactions, token_transfers tables)
Output: same .db (adds views)
        data/analytics/*.csv        (one file per view)
"""

import csv
import logging
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from readme_progress import record_progress

STAGING_DB_PATH = PROJECT_ROOT / "data" / "staging" / "shobitcoin.db"
ANALYTICS_DIR = PROJECT_ROOT / "data" / "analytics"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


VIEWS = {
    "v_daily_activity": """
        CREATE VIEW IF NOT EXISTS v_daily_activity AS
        SELECT
            DATE(timestamp)              AS day,
            COUNT(*)                     AS tx_count,
            COUNT(DISTINCT from_address) AS unique_senders,
            SUM(value_eth)               AS total_value_eth,
            AVG(gas_price_gwei)          AS avg_gas_price_gwei,
            SUM(is_error)                AS failed_tx_count
        FROM transactions
        GROUP BY DATE(timestamp)
        ORDER BY day;
    """,
    "v_daily_token_volume": """
        CREATE VIEW IF NOT EXISTS v_daily_token_volume AS
        SELECT
            DATE(timestamp)              AS day,
            token_symbol,
            COUNT(*)                     AS transfer_count,
            SUM(value_token)             AS total_volume,
            COUNT(DISTINCT from_address) AS unique_senders,
            COUNT(DISTINCT to_address)   AS unique_receivers
        FROM token_transfers
        GROUP BY DATE(timestamp), token_symbol
        ORDER BY day, token_symbol;
    """,
    "v_token_summary": """
        CREATE VIEW IF NOT EXISTS v_token_summary AS
        SELECT
            token_symbol,
            token_name,
            token_contract,
            COUNT(*)                     AS transfer_count,
            SUM(value_token)             AS total_volume,
            COUNT(DISTINCT from_address) AS unique_senders,
            COUNT(DISTINCT to_address)   AS unique_receivers,
            MIN(timestamp)               AS first_seen,
            MAX(timestamp)               AS last_seen
        FROM token_transfers
        GROUP BY token_symbol, token_name, token_contract
        ORDER BY transfer_count DESC;
    """,
    "v_top_senders": """
        CREATE VIEW IF NOT EXISTS v_top_senders AS
        SELECT
            from_address,
            COUNT(*)      AS tx_count,
            SUM(value_eth) AS total_value_eth
        FROM transactions
        GROUP BY from_address
        ORDER BY tx_count DESC;
    """,
    "v_function_usage": """
        CREATE VIEW IF NOT EXISTS v_function_usage AS
        SELECT
            function_name,
            COUNT(*)      AS call_count,
            SUM(is_error) AS failed_count
        FROM transactions
        WHERE function_name IS NOT NULL AND function_name != ''
        GROUP BY function_name
        ORDER BY call_count DESC;
    """,
}


def get_connection() -> sqlite3.Connection:
    if not STAGING_DB_PATH.exists():
        raise FileNotFoundError(
            f"Staging database not found at {STAGING_DB_PATH.resolve()}. "
            "Run scripts/staging/build_sqlite.py first."
        )
    return sqlite3.connect(STAGING_DB_PATH)


def build_views(conn: sqlite3.Connection) -> None:
    for name, ddl in VIEWS.items():
        conn.execute(ddl)
        logger.info("View ready: %s", name)
    conn.commit()


def export_view_to_csv(conn: sqlite3.Connection, view_name: str) -> int:
    cursor = conn.execute(f"SELECT * FROM {view_name}")
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]

    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = ANALYTICS_DIR / f"{view_name}.csv"
    with filepath.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        writer.writerows(rows)

    return len(rows)


def main() -> None:
    conn = get_connection()
    export_counts = {}
    try:
        build_views(conn)
        logger.info("Exporting views to CSV...")
        for view_name in VIEWS:
            row_count = export_view_to_csv(conn, view_name)
            export_counts[view_name] = row_count
            logger.info("  %s.csv -> %s rows", view_name, row_count)
    finally:
        conn.close()
    record_progress(
        "Analytics exports",
        [
            f"Built {len(VIEWS)} SQLite analytical views.",
            "Exported view results to `data/analytics/*.csv` for Power BI.",
        ],
        ", ".join(f"{name}: {count} rows" for name, count in export_counts.items()),
        "Review the CSV outputs and begin KPI analysis.",
    )
    logger.info("Analytics export complete. Files in: %s", ANALYTICS_DIR.resolve())


if __name__ == "__main__":
    main()
