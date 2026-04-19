"""Explodable — live demo.

Showcases the content engine architecture, knowledge base, sample
outputs with per-draft eval scores, and an interactive KB explorer.
"""

import json
import os
from pathlib import Path

import streamlit as st
import requests

# Load env
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in open(env_path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# Streamlit Cloud secrets
if hasattr(st, "secrets"):
    for k, v in st.secrets.items():
        os.environ.setdefault(k, str(v))

SUPA_URL = "https://cgausradwkpvdsiaarkj.supabase.co"
SUPA_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
SUPA_HEADERS = {"apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}"} if SUPA_KEY else {}

DEMO_DIR = Path(__file__).resolve().parent
SAMPLES_DIR = DEMO_DIR / "samples"


def supa_count(table: str, filters: str = "") -> int:
    if not SUPA_KEY:
        return 0
    try:
        r = requests.get(
            f"{SUPA_URL}/rest/v1/{table}?select=id&{filters}",
            headers={**SUPA_HEADERS, "Prefer": "count=exact"},
            timeout=10,
        )
        return int(r.headers.get("Content-Range", "0/0").split("/")[-1])
    except Exception:
        return 0


def supa_query(table: str, select: str = "*", filters: str = "", limit: int = 10) -> list:
    if not SUPA_KEY:
        return []
    try:
        r = requests.get(
            f"{SUPA_URL}/rest/v1/{table}?select={select}&{filters}&limit={limit}",
            headers=SUPA_HEADERS,
            timeout=10,
        )
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []


def load_samples() -> dict:
    scores_path = SAMPLES_DIR / "_scores.json"
    if scores_path.exists():
        return json.loads(scores_path.read_text())
    return {}


CRITERION_LABELS = {
    "governing_thought_opening": "Governing thought in opening",
    "complication_names_felt_tension": "Names felt tension",
    "pattern_naming_insider": "Pattern naming (insider)",
    "integrative_thinking": "Integrative thinking",
    "evidence_specificity_goldilocks": "Evidence specificity",
    "contrarian_causal_mechanism": "Contrarian causal mechanism",
    "forward_to_ceo_arousal": "Forward-to-CEO arousal",
    "headings_standalone_argument": "Headings as arguments",
    "counterargument_handling": "Counterargument handling",
    "conclusion_advances_beyond_summary": "Conclusion advances",
}

TOPICS = {
    "Choose a topic...": None,
    "The Mid-Market Trap — why $10-50M companies make worse purchasing decisions": "T14",
    "Healthcare Procurement — the most fear-driven buying process": "T16",
    "Sales Forecasting — why pipeline numbers are collective fiction": "T07",
    "Vendor Lock-in × Addiction — sunk cost and switching pain": "T27",
    "Procurement × Jury — same biases, different institutions": "T33",
}


# ── Page config ──

st.set_page_config(
    page_title="Explodable — AI Content Engine",
    page_icon="🔬",
    layout="wide",
)

# ── Sidebar ──

with st.sidebar:
    st.title("Explodable")
    st.caption("AI content engine for B2B buyer psychology")

    st.markdown("---")
    st.markdown("### Knowledge Base")

    n_findings = supa_count("findings", "status=eq.active") or 305
    n_rels = supa_count("finding_relationships") or 763

    st.metric("Active findings", n_findings)
    st.metric("Typed relationships", n_rels)
    st.metric("Root anxieties", 5)
    st.metric("Cultural domains", 24)

    st.markdown("---")
    st.markdown("### Pipelines")
    st.markdown("""
    **Production** · `graph.py:671`
    Retrieval → thesis outline → draft → voice-compliance gate → HITL → publish.
    Wiki-based (ADR-0005).

    **Experimental** · `hybrid_graph.py:596`
    Measurement surface. Adds topic routing, graph expansion, adversarial critique,
    revision gating — evaluated before promotion to production.

    **Judge** — 10-criterion rubric, calibrated against a 5-model cluster
    (ρ = 0.841 Opus / 0.782 Sonnet).
    """)

    st.markdown("---")
    st.markdown("""
    **Built with:** Claude Sonnet 4, LangGraph, pgvector, igraph

    **Built through:** AI pair programming with Claude Code

    [GitHub repo](https://github.com/tjkuhns/explodable)
    """)


# ── Main area ──

st.title("Explodable")
st.markdown(
    "An AI content engine that produces analytical essays about B2B buyer psychology, "
    "grounded in a structured knowledge base of behavioral-science findings."
)

# ── Topic selector + generated output ──

st.markdown("---")

selected = st.selectbox("Select a topic to see the engine's output", list(TOPICS.keys()))

topic_id = TOPICS.get(selected)
samples = load_samples()

if topic_id and topic_id in samples:
    sample_data = samples[topic_id]
    draft_path = SAMPLES_DIR / f"{topic_id}.md"

    if draft_path.exists():
        draft_text = draft_path.read_text()

        # Metrics row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Judge score", f"{sample_data['weighted_score']}/57.5")
        with col2:
            st.metric("Unweighted", f"{sample_data['unweighted_score']}/50")
        with col3:
            st.metric("Words", sample_data["word_count"])
        with col4:
            density = sample_data.get("expected_density", "").replace("_", " ").title()
            st.metric("Topic density", density)

        # Per-criterion breakdown
        criteria = sample_data.get("criterion_scores", {})
        if criteria:
            with st.expander("Per-criterion eval scores"):
                cols = st.columns(5)
                for i, (cid, score) in enumerate(criteria.items()):
                    label = CRITERION_LABELS.get(cid, cid)
                    with cols[i % 5]:
                        st.markdown(f"**{label}**")
                        bar_color = "🟢" if score >= 4 else "🟡" if score >= 3 else "🔴"
                        st.markdown(f"{bar_color} {score}/5")

        # The draft itself
        st.markdown("### Generated essay")
        st.markdown(draft_text)

elif selected != "Choose a topic...":
    st.info("Draft not available for this topic.")
else:
    # Default view — show the T14 excerpt
    st.markdown("### Sample output")
    st.markdown("*Select a topic above to see full essays with eval scores, "
                "or browse the sample below:*")
    st.markdown("""
> **The Mid-Market Trap**
>
> The VP of Operations at a \\$25M logistics company stares at three SaaS demos on her
> laptop at 4:47 PM on a Thursday. She's been in meetings since 7 AM, the CEO is asking
> for a vendor recommendation by Friday, and her team of eight stakeholders can't agree
> on basic requirements. She closes the laptop and defaults to "let's table this until Q2"
> — the same decision she made last quarter.
>
> The mid-market sits in a decision-making dead zone. Too big for intuitive founder choices.
> Too small for enterprise decision infrastructure. They don't decide with logic first,
> then hire fear to audit. **They decide with fear first, then hire logic to testify.**
    """)


# ── Aggregate findings ──

st.markdown("---")
st.markdown("## Evaluation harness — aggregate findings")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Thesis outline effect", "+8 points",
              help="Encoding the thesis as a structural schema vs standard prompting. Validated at N=50.")
with col2:
    st.metric("Cross-domain delta", "+9 / +13",
              help="Single-topic bakeoff (N=1): Wiki alone +9, full hybrid pipeline +13 vs production retrieval. N=50 replication confirmed the effect with wide variance (27.7–36.7).")
with col3:
    st.metric("Judge calibration", "ρ = 0.841",
              help="Spearman correlation against a 5-model editorial panel.")

col4, col5, col6 = st.columns(3)
with col4:
    st.metric("CAG for generation", "Failed",
              help="Full-context stuffing scored 26.3 vs 32.0 for focused approaches.")
with col5:
    st.metric("Validation topics", "N=50",
              help="Dense, medium, sparse, cross-domain, and out-of-distribution conditions.")
with col6:
    st.metric("Cost per draft", "~$0.03",
              help="Phase 1 bakeoff estimate (N=5 topics). Current production (Wiki-based) runs ~$0.03 per draft; the prior pipeline it replaced ran ~$0.30. ADR-0005.")


# ── KB explorer ──

st.markdown("---")
st.markdown("## Knowledge base explorer")

anxiety_filter = st.selectbox(
    "Filter by root anxiety",
    ["All", "helplessness", "insignificance", "isolation", "meaninglessness", "mortality"]
)

if anxiety_filter == "All":
    findings = supa_query(
        "findings",
        select="claim,academic_discipline,confidence_score,root_anxieties,cultural_domains",
        filters="status=eq.active&order=confidence_score.desc",
        limit=20,
    )
else:
    findings = supa_query(
        "findings",
        select="claim,academic_discipline,confidence_score,root_anxieties,cultural_domains",
        filters=f"status=eq.active&root_anxieties=cs.{{{anxiety_filter}}}&order=confidence_score.desc",
        limit=20,
    )

if findings:
    for f in findings:
        with st.expander(f"**{f['claim'][:100]}{'...' if len(f['claim']) > 100 else ''}**"):
            st.markdown(f"**Full claim:** {f['claim']}")
            st.markdown(f"**Discipline:** {f['academic_discipline']}")
            st.markdown(f"**Confidence:** {f['confidence_score']:.2f}")
            st.markdown(f"**Anxieties:** {', '.join(f.get('root_anxieties', []))}")
            domains = f.get('cultural_domains', [])
            if domains:
                st.markdown(f"**Domains:** {', '.join(domains)}")
else:
    st.info("Connect to Supabase to browse findings.")


# ── Architecture ──

st.markdown("---")
st.markdown("## Architecture")
st.markdown(
    "Two graphs share one knowledge base. The production graph runs every draft; "
    "the experimental graph is the measurement surface where architecture changes "
    "are evaluated before being promoted. The split lets architecture decisions be "
    "driven by measured results rather than opinion."
)

st.markdown("### Production pipeline")
st.caption("`src/content_pipeline/graph.py:671` · runs every draft · Wiki-based retrieval (ADR-0005)")
st.code("""
calendar_trigger ──── scheduled topic from editorial calendar
       │
kb_retriever ──────── multi-query retrieval + decay-weighted scoring
       │
content_selector ──── ranks + enforces ≥1 cross-domain finding
       │
outline_generator ─── thesis-constrained outline
       │                   (fear-commit → logic-recruit → testimony-deploy)
HITL gate ─────────── outline review
       │
draft_generator ───── voice profile, inline citation markers
       │
bvcs_scorer ───────── voice compliance (fail → revise, max 3 loops)
       │
HITL gate ─────────── draft review
       │
publisher_stub ────── write markdown to disk
""", language=None)

st.markdown("### Experimental pipeline")
st.caption("`src/content_pipeline/experimental/hybrid_graph.py:596` · measurement surface, not production · adversarial critique + revision gating live here because they're being evaluated, not because they're live")
st.code("""
topic_router ───────── classifies topic, routes to retrieval strategy
  ├─ wiki_selector ── reads KB index, picks findings across domains
  ├─ vector_retriever ── pgvector similarity search within cluster
  └─ graph_walker ──── PPR traversal + MMR diversity reranking
       │
graph_expander ────── adds cross-domain findings via relationship graph
       │
outline_generator ─── thesis-constrained
       │
draft_generator ───── focused context, voice profile, citations
       │
bvcs_scorer ───────── voice compliance (fail → revise, max 3)
       │
adversarial_critic ── a different model reads full KB + draft
       │
revision_gate ─────── Pareto filter: improve without regressing
       │
HITL gate ─────────── draft review → publisher
""", language=None)

st.markdown("---")
st.caption("Built by Tom Kuhns · Youngstown, OH · [GitHub](https://github.com/tjkuhns/explodable)")
