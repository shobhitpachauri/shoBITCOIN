# shoBITCOIN

## Idea

**shoBITCOIN** is an open-source project for building a Digital Asset Due
Diligence and Risk Intelligence Platform.

The platform will combine blockchain data, smart-contract analysis,
tokenomics, financial analytics, governance, cybersecurity, and regulatory
research into explainable digital-asset assessments.

The central question is:

> Before an institution interacts with a digital asset or protocol, what is
> it interacting with, what could go wrong, what controls exist, and what
> evidence supports the conclusion?

Every finding must follow this chain:

```text
Question -> Evidence -> Rule -> Finding -> Risk Level -> Confidence
```

The system must not produce unexplained black-box scores.

## Project Info

| Area | Current decision |
| --- | --- |
| Network | Ethereum mainnet for analysis; Sepolia for learning contracts |
| Protocol | Aave V3 |
| Main contract | `0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2` |
| Data source | Etherscan free API |
| Raw data | Timestamped JSON in `data/raw/etherscan/` |
| Staged data | SQLite in `data/staging/shobitcoin.db` |
| Main tools | Python, SQLite, SQL, Power BI, Solidity |
| Cost goal | $0 recurring cost |

Free and public data sources will be used wherever possible. Data will never
be invented; unavailable data will be labeled `Data unavailable.` Estimates
will be clearly identified.

## Steps Achieved

- Created the project repository and initial Web3 learning workflow.
- Created and deployed the `shoBITCOIN` ERC-20 token on Ethereum Sepolia.
- Created and deployed the `SimpleEscrow` contract on Ethereum Sepolia.
- Practiced wallets, transactions, gas, Wei, internal transfers, and Etherscan verification.
- Added an Etherscan extractor for normal transactions (`txlist`) and ERC-20 transfers (`tokentx`).
- Extracted raw Aave V3 Pool data from Ethereum mainnet.
- Added SQLite staging for cleaned, typed, and deduplicated records.
- Confirmed the staging database contains 2,000 transactions and 58 unique token transfers.

## Current Progress

**Current stage: SQLite staging completed.**

The next planned step is to build analytical queries against the staged data,
starting with transaction counts, date ranges, active addresses, transfer
activity, and other basic protocol KPIs.

Longer-term work will cover:

- Transaction and market analytics
- Token and smart-contract risk analysis
- Performance/KPI and risk Power BI dashboards
- AI-assisted research and reporting

AI will explain evidence and findings, but it must not invent evidence or
replace the underlying rules.

## Daily Progress Log

Use this section to record one short update after each work session.

### 2026-09-15

- Added SQLite staging and duplicate inspection scripts.
- Built `data/staging/shobitcoin.db` from the extracted Etherscan data.
- Confirmed duplicate token-transfer handling is working.

### 2026-09-15 — SQLite staging

- Loaded and typed raw transaction and token-transfer JSON.
- Applied duplicate protection with primary and unique keys.
- Created `data/staging/shobitcoin.db`.
- Result: 2000 transactions and 58 unique token transfers in SQLite; 0 and 0 new rows this run.
- Next step: Run `python scripts/analytics/build_analytics.py`.

### 2026-09-15 — Analytics exports

- Built 5 SQLite analytical views.
- Exported view results to `data/analytics/*.csv` for Power BI.
- Result: v_daily_activity: 2 rows, v_daily_token_volume: 49 rows, v_token_summary: 24 rows, v_top_senders: 871 rows, v_function_usage: 11 rows
- Next step: Review the CSV outputs and begin KPI analysis.

### Next update

- Date:
- Work completed:
- Validation/result:
- Next step:

## Setup

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Add the Etherscan API key to `.env`, then run extraction:

```powershell
python scripts\extract\etherscan_extract.py --max-pages 2
```

Build or refresh the SQLite staging database:

```powershell
python scripts\staging\build_sqlite.py
```

## Project Structure

```text
shoBITCOIN/
├── .env                  # local API key; never commit
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── contracts/
│   ├── shoBITCOIN.sol
│   └── SimpleEscrow.sol
├── data/
│   ├── raw/etherscan/    # generated raw JSON, git-ignored
│   └── staging/          # generated SQLite database
├── scripts/
│   ├── extract/
│   │   └── etherscan_extract.py
│   └── staging/
│       ├── build_sqlite.py
│       └── inspect_duplicates.py
└── docs/
    ├── escrow.md
    └── sqlite.md
```

## Disclaimer

shoBITCOIN is an educational, experimental, and research project. It does
not provide investment advice and does not replace professional smart-contract
audits, financial analysis, legal advice, cybersecurity assessments, or
regulatory advice.
