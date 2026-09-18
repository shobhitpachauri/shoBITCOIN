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
| Main tools | Python, SQLite, SQL, Power BI, Solidity, Streamlit, Groq |
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

**Current stage: analytics exports completed; RAG chatbot layer added.**

The transaction pipeline now includes SQLite staging and analytical CSV exports
for Power BI. A RAG chatbot layer has also been added for research and risk
questions.

Longer-term work will cover:

- Transaction and market analytics
- Token and smart-contract risk analysis
- Performance/KPI and risk Power BI dashboards
- AI-assisted research and reporting grounded in retrieved sources

AI will explain evidence and findings, but it must not invent evidence or
replace the underlying rules.

## RAG Risk Chatbot

The chatbot combines three explicitly separated source types:

1. **External framework context** from published research papers such as EY's
    Token Due Diligence paper.
2. **Project interpretation** from shoBITCOIN's own framework-mapping and rule
    documents.
3. **Observed on-chain evidence** produced by the existing
    `contract_risk_scan.py` scanner for a specified contract address.

The model is used to explain supplied evidence. It must not invent findings or
blend framework claims, project rules, and contract evidence into one unlabeled
claim. SQLite stores the local document chunks and lightweight retrieval uses
token overlap, while Groq provides the free-tier OpenAI-compatible LLM endpoint.

Place source documents in the appropriate folder:

```text
data/research_papers/external/      # published papers and frameworks
data/research_papers/project_docs/  # shoBITCOIN interpretation documents
```

Ingest the documents into the local SQLite document store:

```powershell
python scripts\rag\ingest_papers.py
```

Add both API keys to `.env`:

```text
ETHERSCAN_API_KEY=your_etherscan_key
GROQ_API_KEY=your_groq_key
```

Ask a question from the command line:

```powershell
python scripts\rag\rag_query.py "What makes a contract's admin risky?"
python scripts\rag\rag_query.py "Is this contract risky?" --address 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2
```

Start the Streamlit interface:

```powershell
streamlit run scripts\app\app.py
```

The chatbot is a research prototype and does not replace professional audits,
legal advice, or financial advice.

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
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Add both API keys to `.env`, then run extraction:

```text
ETHERSCAN_API_KEY=your_etherscan_key
GROQ_API_KEY=your_groq_key
```

Run extraction:

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
│   ├── staging/          # generated SQLite database
│   ├── analytics/        # generated CSV exports for Power BI
│   ├── rag_documents.db  # generated local RAG document store
│   └── research_papers/
│       ├── external/     # published framework documents
│       └── project_docs/ # project interpretation documents
├── scripts/
│   ├── extract/
│   │   └── etherscan_extract.py
│   ├── staging/
│       ├── build_sqlite.py
│       └── inspect_duplicates.py
│   ├── rag/
│   │   ├── ingest_papers.py
│   │   └── rag_query.py
│   └── app/
│       └── app.py
└── docs/
    ├── escrow.md
    └── sqlite.md
```

## Disclaimer

shoBITCOIN is an educational, experimental, and research project. It does
not provide investment advice and does not replace professional smart-contract
audits, financial analysis, legal advice, cybersecurity assessments, or
regulatory advice.
