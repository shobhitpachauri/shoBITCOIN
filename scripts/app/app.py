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
import re
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rag"))
from rag_query import ask

st.set_page_config(page_title="Digital Asset Risk Intelligence", page_icon="◈", layout="wide")

st.markdown(
    """
    <style>
        .block-container { max-width: 1180px; padding-top: 2.25rem; padding-bottom: 3rem; }
        .hero { padding: 1.75rem 2rem; border: 1px solid #2c4057; border-radius: 12px;
            background: linear-gradient(135deg, #111a27 0%, #162235 100%); margin-bottom: 1.5rem; }
        .hero-kicker { color: #65b8ff; font-size: .72rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
        .hero h1 { margin: .45rem 0 .5rem; color: #f5f7fa; font-size: 2.25rem; letter-spacing: .01em; }
        .hero p { color: #aab8ca; margin: 0; max-width: 820px; line-height: 1.55; }
        .brand-mark { color: #71839a; font-size: .76rem; margin-top: 1rem; letter-spacing: .08em; text-transform: uppercase; }
        .section-title { color: #65b8ff; font-size: .72rem; font-weight: 700; letter-spacing: .13em;
                 text-transform: uppercase; margin: 1.4rem 0 .55rem; }
    .source-chip { display: inline-block; padding: .25rem .55rem; margin: .15rem .2rem .15rem 0;
                   border: 1px solid #30445d; border-radius: 999px; color: #c8d7e8; font-size: .78rem; }
    [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea { border-radius: 10px; }
    div.stButton > button { width: 100%; border-radius: 10px; border: 1px solid #4da3ff;
                            background: #1677c8; color: white; font-weight: 700; }
    div.stButton > button:hover { background: #258de0; border-color: #8acbff; }
    </style>
    <div class="hero">
    <div class="hero-kicker">Digital asset due diligence</div>
    <h1>Digital Asset Risk Intelligence</h1>
    <p>Research-grade contract analysis grounded in published frameworks, project rules, and observed on-chain evidence.</p>
    <div class="brand-mark">shoBITCOIN research platform</div>
    </div>
    """,
    unsafe_allow_html=True,
)


def render_answer(answer: str) -> None:
    """Render contract answers by their fixed headings instead of one text block."""
    sections = re.split(r"(?m)^## (Contract Information|Risk Summary|Detailed Findings)\s*$", answer)
    if len(sections) < 3:
        st.markdown(answer)
        return

    st.markdown("<div class='section-title'>Analysis</div>", unsafe_allow_html=True)
    for index in range(1, len(sections), 2):
        title = sections[index]
        content = sections[index + 1].strip()
        with st.container(border=True):
            st.markdown(f"### {title}")
            st.markdown(content)

st.markdown("<div class='section-title'>Assessment workspace</div>", unsafe_allow_html=True)
address = st.text_input("Contract address", placeholder="Optional · 0x...", help="Paste a deployed Ethereum contract address to include live Etherscan evidence.")
question = st.text_area("Research question", placeholder="Who controls this contract, and what could they change?", height=110)
ask_clicked = st.button("Run assessment", type="primary")

if ask_clicked and question.strip():
    with st.spinner("Retrieving context and generating answer..."):
        try:
            clean_address = address.strip() if address.strip() else None
            result = ask(question, clean_address)

            render_answer(result["answer"])

            with st.expander("Evidence and source register"):
                chunks = result["framework_chunks"]
                if chunks:
                    st.markdown("<div class='section-title'>Retrieved framework context</div>", unsafe_allow_html=True)
                    for c in chunks:
                        meta = c["metadata"]
                        label = (
                            "External Framework"
                            if meta["source_category"] == "external_framework"
                            else "Project Interpretation"
                        )
                        st.markdown(
                            f"<span class='source-chip'>{label}</span> "
                            f"**{meta['source_file']}**, page {meta['page_number']}",
                            unsafe_allow_html=True,
                        )
                        st.text(c["text"][:400] + ("..." if len(c["text"]) > 400 else ""))
                else:
                    st.info("No framework passages retrieved. Have you run scripts/rag/ingest_papers.py yet?")

                if clean_address:
                    report = result["contract_report"]
                    if report:
                        st.markdown("<div class='section-title'>Observed on-chain evidence</div>", unsafe_allow_html=True)
                        st.code(clean_address, language="text")
                        for f in report["findings"]:
                            with st.container(border=True):
                                st.markdown(f"**{f['pillar']}**  ")
                                st.markdown(f"{f['finding']}")
                                st.caption(f"{f['risk_level']} risk · {f['confidence']} confidence · {f['verification_method']}")
                    else:
                        st.warning("ETHERSCAN_API_KEY not set — could not pull on-chain evidence.")
        except Exception as e:
            st.error(f"Something went wrong: {e}")

st.divider()
st.caption(
    "shoBITCOIN research platform · Ethereum data via Etherscan · EY Token Due Diligence · "
    "Groq inference · local SQLite retrieval"
)
