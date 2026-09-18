"""
ingest_papers.py

RAG ingestion step. Reads PDF and text/markdown files from
data/research_papers/{external,project_docs}/, chunks them, and stores the
chunks in a local SQLite document store. Retrieval is performed later with
lightweight token-overlap search, so no native vector database or C++ build
tools are required.

Folder convention (this drives labeling, not just organization):
    data/research_papers/external/      -> external framework documents
                                            (EY, Basel, OWASP, FATF, MiCA PDFs)
    data/research_papers/project_docs/  -> shoBITCOIN's own interpretation
                                            documents (e.g. EY_FRAMEWORK_MAPPING.md)

Every chunk is tagged with source_category so the chatbot can always tell
the user which kind of source an answer is drawing from - never blending
"what EY's paper says" with "what shoBITCOIN decided to do about it"
without saying which is which.

Requirements:
    pip install -r requirements.txt   (adds pypdf)

Setup:
    mkdir -p data/research_papers/external data/research_papers/project_docs
    - Put EY's PDF (and Basel/OWASP/FATF/MiCA PDFs later) in external/
    - Put EY_FRAMEWORK_MAPPING.md (and PROJECT_CONTEXT_PROMPT.md if desired) in project_docs/

Usage:
    python scripts/rag/ingest_papers.py
"""

import logging
import sqlite3
from pathlib import Path

from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = PROJECT_ROOT / "data" / "research_papers"
RAG_DB_PATH = PROJECT_ROOT / "data" / "rag_documents.db"

CHUNK_SIZE_CHARS = 1200
CHUNK_OVERLAP_CHARS = 200

SOURCE_CATEGORY_BY_FOLDER = {
    "external": "external_framework",
    "project_docs": "project_interpretation",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def extract_text_from_pdf(filepath: Path) -> list:
    """Returns a list of (page_number, text) tuples."""
    reader = PdfReader(str(filepath))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((i, text))
    return pages


def extract_text_from_textfile(filepath: Path) -> list:
    text = filepath.read_text(encoding="utf-8")
    return [(1, text)]  # whole file treated as "page 1"


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list:
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return [c.strip() for c in chunks if c.strip()]


def process_file(filepath: Path, source_category: str) -> list:
    """Returns a list of {text, metadata} dicts for one file."""
    suffix = filepath.suffix.lower()
    if suffix == ".pdf":
        pages = extract_text_from_pdf(filepath)
    elif suffix in (".txt", ".md"):
        pages = extract_text_from_textfile(filepath)
    else:
        logger.warning(f"Skipping unsupported file type: {filepath.name}")
        return []

    records = []
    for page_number, page_text in pages:
        for chunk_index, chunk in enumerate(chunk_text(page_text)):
            records.append({
                "text": chunk,
                "metadata": {
                    "source_file": filepath.name,
                    "source_category": source_category,
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                },
            })
    return records


def get_connection() -> sqlite3.Connection:
    RAG_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(RAG_DB_PATH)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_category TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL
        )
    """)
    connection.commit()
    return connection


def main():
    if not RESEARCH_DIR.exists():
        logger.error(
            f"{RESEARCH_DIR} does not exist. Create data/research_papers/external/ "
            f"and data/research_papers/project_docs/ and add files first."
        )
        return

    all_records = []
    for folder_name, source_category in SOURCE_CATEGORY_BY_FOLDER.items():
        folder = RESEARCH_DIR / folder_name
        if not folder.exists():
            logger.warning(f"{folder} not found, skipping.")
            continue
        for filepath in sorted(folder.iterdir()):
            if filepath.is_file():
                logger.info(f"Processing {filepath} as '{source_category}'...")
                records = process_file(filepath, source_category)
                logger.info(f"  -> {len(records)} chunk(s)")
                all_records.extend(records)

    if not all_records:
        logger.warning("No documents found to ingest.")
        return

    connection = get_connection()
    try:
        connection.execute("DELETE FROM document_chunks")
        connection.executemany(
            """
            INSERT INTO document_chunks
            (id, text, source_file, source_category, page_number, chunk_index)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    f"{r['metadata']['source_category']}_{r['metadata']['source_file']}_"
                    f"{r['metadata']['page_number']}_{r['metadata']['chunk_index']}",
                    r["text"],
                    r["metadata"]["source_file"],
                    r["metadata"]["source_category"],
                    r["metadata"]["page_number"],
                    r["metadata"]["chunk_index"],
                )
                for r in all_records
            ],
        )
        connection.commit()
        total = connection.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
    finally:
        connection.close()

    logger.info("Ingestion complete. Stored %s chunk(s) in %s", total, RAG_DB_PATH)


if __name__ == "__main__":
    main()
