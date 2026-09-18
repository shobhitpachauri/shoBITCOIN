"""
rag_query.py

Core retrieval-augmented answer logic. For a given question:
    1. Retrieves relevant framework passages from ChromaDB (local, free)
    2. Optionally scans a specific contract address for live on-chain
       evidence, reusing contract_risk_scan.py directly (no duplicated logic)
    3. Builds a prompt that keeps these two sources - plus the project's
       own proposed rules - explicitly labeled and separate
    4. Sends it to a Groq-hosted open-weight model (free tier) and returns
       the answer

The model is explicitly instructed not to state anything as fact unless
it's grounded in the supplied context - it does not invent findings.
This mirrors the project's core rule: AI explains evidence, it doesn't
manufacture it.

Requirements:
    pip install -r requirements.txt   (adds chromadb, pypdf, openai)

Setup:
    - Run scripts/rag/ingest_papers.py at least once first
    - Add GROQ_API_KEY to .env (free, no card - console.groq.com)
    - ETHERSCAN_API_KEY should already be in .env from earlier steps

Usage (standalone test, no UI):
    python scripts/rag/rag_query.py "What makes a contract's admin risky?"
    python scripts/rag/rag_query.py "Is this contract risky?" --address 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Reuse the ingestion module's collection helper and the risk scanner directly,
# rather than re-implementing either.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "risk"))
import ingest_papers
import contract_risk_scan

load_dotenv(PROJECT_ROOT / ".env")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.1-8b-instant"
TOP_K_CHUNKS = 5

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_groq_client() -> OpenAI:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY not set. Add it to your .env file (free key from console.groq.com).")
        sys.exit(1)
    return OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)


def retrieve_framework_context(question: str, top_k: int = TOP_K_CHUNKS) -> list:
    collection = ingest_papers.get_collection()
    if collection.count() == 0:
        logger.warning("ChromaDB collection is empty. Run scripts/rag/ingest_papers.py first.")
        return []
    results = collection.query(query_texts=[question], n_results=top_k)
    chunks = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        chunks.append({"text": doc, "metadata": meta})
    return chunks


def get_contract_evidence(address: str, etherscan_api_key: str) -> dict:
    """Runs the existing risk scanner live and returns its evidence + findings."""
    evidence = contract_risk_scan.gather_evidence(address, etherscan_api_key)
    findings = contract_risk_scan.evaluate_rules(evidence)
    return {"evidence": evidence, "findings": findings}


def build_prompt(question: str, framework_chunks: list, contract_report: dict = None) -> str:
    parts = [
        "You are an assistant for shoBITCOIN, a digital asset due diligence research project. "
        "Answer the user's question using ONLY the information provided below. "
        "Clearly distinguish three kinds of information whenever you use them:\n"
        "1. EXTERNAL FRAMEWORK CONTEXT - excerpts from published research papers (e.g. EY).\n"
        "2. PROJECT INTERPRETATION - shoBITCOIN's own proposed rules derived from those frameworks, "
        "not claims made by the external framework itself.\n"
        "3. OBSERVED ON-CHAIN EVIDENCE - specific, factual findings from scanning one real contract.\n"
        "Never state something as a fact unless it appears in one of these sections below. "
        "If the provided information does not answer the question, say so explicitly rather than guessing."
    ]

    if framework_chunks:
        parts.append("\n--- FRAMEWORK / PROJECT CONTEXT (retrieved) ---")
        for chunk in framework_chunks:
            meta = chunk["metadata"]
            label = "EXTERNAL FRAMEWORK" if meta["source_category"] == "external_framework" else "PROJECT INTERPRETATION"
            parts.append(f"[{label} - {meta['source_file']}, page {meta['page_number']}]\n{chunk['text']}")

    if contract_report:
        parts.append("\n--- OBSERVED ON-CHAIN EVIDENCE (this specific contract) ---")
        parts.append(f"Contract address: {contract_report['evidence']['address']}")
        for f in contract_report["findings"]:
            parts.append(
                f"- [{f['pillar']}] Question: {f['question']} | Evidence: {f['evidence']} | "
                f"Finding: {f['finding']} | Risk: {f['risk_level']} | Confidence: {f['confidence']} | "
                f"Verification method: {f['verification_method']}"
            )

    parts.append(f"\n--- QUESTION ---\n{question}")
    return "\n".join(parts)


def ask(question: str, address: str = None) -> dict:
    framework_chunks = retrieve_framework_context(question)

    contract_report = None
    if address:
        etherscan_api_key = os.environ.get("ETHERSCAN_API_KEY")
        if not etherscan_api_key:
            logger.warning("ETHERSCAN_API_KEY not set - cannot pull on-chain evidence for the address.")
        else:
            logger.info(f"Scanning {address} for fresh on-chain evidence...")
            contract_report = get_contract_evidence(address, etherscan_api_key)

    prompt = build_prompt(question, framework_chunks, contract_report)

    client = get_groq_client()
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return {
        "answer": response.choices[0].message.content,
        "framework_chunks": framework_chunks,
        "contract_report": contract_report,
    }


def main():
    parser = argparse.ArgumentParser(description="Ask the shoBITCOIN RAG chatbot a question, standalone (no UI).")
    parser.add_argument("question", help="Your question")
    parser.add_argument("--address", default=None, help="Optional contract address for live on-chain evidence")
    args = parser.parse_args()

    result = ask(args.question, args.address)
    print("\n--- ANSWER ---")
    print(result["answer"])


if __name__ == "__main__":
    main()
