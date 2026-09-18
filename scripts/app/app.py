"""
app.py

Streamlit front-end for the shoBITCOIN risk chatbot. Lets the user ask
a question and optionally supply a contract address; the answer is
grounded in retrieved framework/project-rule passages and, if an address
is given, live on-chain evidence - with all sources shown transparently
underneath the answer so nothing is a black box.

Requirements:
    pip install -r requirements.txt   (adds streamlit, chromadb, pypdf, openai)

Setup:
    1. Run scripts/rag/ingest_papers.py at least once first
    2. Make sure .env has GROQ_API_KEY and ETHERSCAN_API_KEY set

Usage:
    streamlit run scripts/app/app.py
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rag"))
from rag_query import ask

st.set_page_config(page_title="shoBITCOIN Risk Chatbot", page_icon="🔍")

st.title("🔍 shoBITCOIN Risk Chatbot")
st.caption(
    "Answers are grounded in EY's Token Due Diligence framework and, optionally, live on-chain "
    "evidence for a specific contract. This is a research prototype, not financial or legal advice, "
    "and it does not replace a professional security audit."
)

address = st.text_input(
    "Contract address (optional) — paste one to include live on-chain evidence in the answer"
)
question = st.text_area("Your question")

if st.button("Ask") and question.strip():
    with st.spinner("Retrieving context and generating answer..."):
        try:
            clean_address = address.strip() if address.strip() else None
            result = ask(question, clean_address)

            st.markdown("### Answer")
            st.write(result["answer"])

            with st.expander("Show sources used for this answer"):
                chunks = result["framework_chunks"]
                if chunks:
                    st.markdown("**Framework / project context retrieved:**")
                    for c in chunks:
                        meta = c["metadata"]
                        label = (
                            "External Framework"
                            if meta["source_category"] == "external_framework"
                            else "Project Interpretation"
                        )
                        st.markdown(f"- **[{label}]** {meta['source_file']}, page {meta['page_number']}")
                        st.text(c["text"][:400] + ("..." if len(c["text"]) > 400 else ""))
                else:
                    st.info("No framework passages retrieved. Have you run scripts/rag/ingest_papers.py yet?")

                if clean_address:
                    report = result["contract_report"]
                    if report:
                        st.markdown(f"**Live on-chain evidence for `{clean_address}`:**")
                        for f in report["findings"]:
                            st.markdown(
                                f"- **[{f['risk_level']} risk / {f['confidence']} confidence]** "
                                f"({f['pillar']}) {f['finding']} "
                                f"— _verification: {f['verification_method']}_"
                            )
                    else:
                        st.warning("ETHERSCAN_API_KEY not set — could not pull on-chain evidence.")
        except Exception as e:
            st.error(f"Something went wrong: {e}")

st.divider()
st.caption(
    "Built on Ethereum + Aave data via Etherscan. Framework: EY Token Due Diligence. "
    "Powered by Groq (free tier, open-weight models) + local embeddings via ChromaDB's built-in MiniLM."
)
