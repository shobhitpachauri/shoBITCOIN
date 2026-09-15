# Using SQLite in shoBITCOIN

A practical guide for working with the SQLite database in this project —
what it is, how to inspect it, and how to query it. You already know SQL,
so this focuses on the SQLite-specific and tooling parts, not general SQL.

---

## What SQLite actually is

SQLite is not a server you run — it's a **single file on disk**
(e.g. `data/staging/shobitcoin.db`) that contains your whole database:
tables, indexes, everything. No install, no service to start/stop, no
connection string with a host/port. Python has SQLite support built in
(`import sqlite3`), so no extra dependency is even needed for the Python
side.

This is why it fits the project: zero cost, zero infra, and it disappears
entirely if you just delete the file.

## How you'll interact with it (three ways)

### 1. From Python (how the pipeline writes to it)

```python
import sqlite3

conn = sqlite3.connect("data/staging/shobitcoin.db")
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM transactions")
print(cursor.fetchone())

conn.close()
```

The staging script (next thing we'll build) does this automatically — you
won't normally need to write this yourself, but it's useful to understand
what's happening under the hood.

### 2. A GUI tool, to actually look at the data

Recommended: **DB Browser for SQLite** — free, open-source, no account
needed. https://sqlitebrowser.org/

- Download and install it
- Open your `.db` file directly in it
- "Browse Data" tab to scroll through tables like a spreadsheet
- "Execute SQL" tab to run ad-hoc SQL queries and see results instantly

This is the easiest way to sanity-check that the pipeline actually wrote
what you expect, without writing any code.

### 3. Directly inside VS Code (optional, but convenient)

Install the **SQLite Viewer** or **SQLTools + SQLTools SQLite driver**
extension from the VS Code marketplace (both free). Either lets you:

- Open a `.db` file and browse tables in a side panel
- Run SQL queries against it without leaving your editor

You don't need both DB Browser and a VS Code extension — pick whichever
you find easier to work with. DB Browser is the more beginner-friendly
standalone option.

## How SQLite fits into our pipeline

```text
Raw JSON (data/raw/etherscan/)
    → staging script reads JSON, cleans/types it
    → writes rows into SQLite tables (data/staging/shobitcoin.db)
    → analytical queries (daily tx counts, volume, unique addresses) run as SQL against those tables
    → Power BI connects to the SQLite file (via ODBC driver) or reads CSV exports of query results
```

We'll design one table per dataset to start:

- `transactions` — cleaned rows from `txlist`
- `token_transfers` — cleaned rows from `tokentx`

Each row will carry the source contract address and a proper datetime, so
queries like "transactions per day" or "unique addresses per week" are
simple `GROUP BY` queries.

## Basic SQLite-flavored SQL notes (small differences from other databases)

- Data types are flexible ("type affinity") — SQLite won't strictly reject
a text value in an integer column the way Postgres would. We'll still
define types properly in our `CREATE TABLE` statements for clarity, but
don't be surprised if SQLite is more lenient than you're used to.
- No `RIGHT JOIN` or `FULL OUTER JOIN` support (rarely needed here).
- Timestamps aren't a native type — we'll store them as ISO 8601 text
(`"2024-01-15T10:30:00"`) or as Unix epoch integers, and convert as
needed in queries with `datetime()`.
- To inspect a table's structure from SQL: `PRAGMA table_info(transactions);`
- To list all tables: `SELECT name FROM sqlite_master WHERE type='table';`

## Common commands once the staging script exists

Open the `.db` file in DB Browser, or run these from Python/CLI:

```sql
-- Row counts
SELECT COUNT(*) FROM transactions;

-- Date range covered
SELECT MIN(timestamp), MAX(timestamp) FROM transactions;

-- Transactions per day
SELECT DATE(timestamp) AS day, COUNT(*) AS tx_count
FROM transactions
GROUP BY day
ORDER BY day;

-- Unique addresses interacting with the contract
SELECT COUNT(DISTINCT from_address) FROM transactions;
```

## What's next

Once you're comfortable with the above, the next script we build will:

1. Read the raw JSON files from `data/raw/etherscan/`
2. Create the SQLite database and tables (if they don't exist yet)
3. Clean and insert the data, avoiding duplicate rows on re-runs

Let me know when you're ready for that script.
