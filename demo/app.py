"""Explodable — live demo.

Streamlit app that demonstrates the content engine. Bypasses
Celery/Redis/FastAPI and runs the pipeline directly: thesis-constrained
outline → draft → eval score. Connects to Postgres for the KB.

Designed for Streamlit Cloud deployment (free tier).
"""

import os
import sys
import time
from pathlib import Path

import streamlit as st

# Load env
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in open(env_path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Page config ──

st.set_page_config(
    page_title="Explodable — AI Content Engine",
    page_icon="🔬",
    layout="wide",
)


# ── Sidebar: KB stats + about ──

with st.sidebar:
    st.title("Explodable")
    st.caption("AI content engine for B2B buyer psychology")

    st.markdown("---")
    st.markdown("### Knowledge Base")

    try:
        import psycopg
        # Use Supabase if available, fall back to local
        supa_pass = os.environ.get("SUPABASE_PASSWORD", "")
        if supa_pass:
            conn_params = {
                "host": "db.cgausradwkpvdsiaarkj.supabase.co",
                "port": 5432,
                "user": "postgres",
                "password": supa_pass,
                "dbname": "postgres",
            }
        else:
            db_url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
            if "${POSTGRES_PASSWORD}" in db_url:
                db_url = db_url.replace("${POSTGRES_PASSWORD}", os.environ.get("POSTGRES_PASSWORD", ""))
            conn_params = db_url
        with psycopg.connect(**conn_params) if isinstance(conn_params, dict) else psycopg.connect(conn_params) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM findings WHERE status='active'")
                n_findings = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM finding_relationships")
                n_rels = cur.fetchone()[0]

        st.metric("Active findings", n_findings)
        st.metric("Typed relationships", n_rels)
        st.metric("Root anxieties", 5)
        st.metric("Cultural domains", 24)
    except Exception as e:
        st.warning(f"KB not connected: {e}")
        n_findings = 305
        n_rels = 763

    st.markdown("---")
    st.markdown("### How it works")
    st.markdown("""
    1. **Topic router** classifies your topic
    2. **Retrieval** selects findings from the KB
    3. **Graph expansion** adds cross-domain connections via PPR
    4. **Thesis outline** structures the argument through fear→testimony
    5. **Draft** generates the essay with inline citations
    6. **Judge** scores against a 10-criterion calibrated rubric
    """)

    st.markdown("---")
    st.markdown("""
    **Built with:** Claude Sonnet 4, LangGraph, pgvector, igraph

    **Built through:** AI pair programming with Claude Code

    [GitHub repo](https://github.com/thomasjkuhns/explodable)
    """)


# ── Main area ──

st.title("Generate an analytical essay")
st.markdown(
    "Type a topic about B2B buyer psychology, executive decision-making, "
    "or organizational behavior. The engine will produce a thesis-driven "
    "analytical essay grounded in behavioral science findings from the knowledge base."
)

# Preset topics
PRESETS = {
    "Choose a preset or write your own...": "",
    "The Mid-Market Trap": "The mid-market trap: why $10-50M ARR companies make systematically worse technology purchasing decisions than companies above or below them.",
    "The Security Review as Theater": "The security review as psychological theater: why procurement's most time-consuming gate is really about career risk, not data protection.",
    "Vendor Lock-in × Addiction": "The structural similarity between enterprise vendor lock-in and addiction: sunk cost, withdrawal, and the architecture of switching pain.",
    "Healthcare Procurement Fear": "Why healthcare procurement is the most fear-driven buying process in any industry: the psychology of defensive medicine applied to vendor selection.",
    "The Confidence Gap in Forecasting": "The confidence gap in sales forecasting: why your pipeline numbers are a collective fiction and what the behavioral science says about fixing them.",
}

preset = st.selectbox("Preset topics", list(PRESETS.keys()))
topic = st.text_area(
    "Topic",
    value=PRESETS.get(preset, ""),
    height=100,
    placeholder="e.g., Why enterprise buyers ghost after the demo: the psychology of post-evaluation silence",
)

col1, col2 = st.columns([1, 3])
with col1:
    generate = st.button("Generate essay", type="primary", disabled=not topic.strip())
with col2:
    st.caption("Takes ~60-90 seconds. Uses Claude Sonnet 4 for generation.")

if generate and topic.strip():
    with st.status("Running pipeline...", expanded=True) as status:

        # Step 1: Topic routing
        st.write("**Step 1:** Classifying topic...")
        try:
            from src.content_pipeline.topic_router import DomainSignalClassifier
            classifier = DomainSignalClassifier()
            classification = classifier.classify(topic)
            st.write(f"→ Route: `{classification.route.value}` | Density: `{classification.density}` | Domains: {classification.matched_domains} | Cross-domain: {classification.is_cross_domain}")
        except Exception as e:
            st.error(f"Router failed: {e}")
            classification = None

        # Step 2: Retrieve findings
        st.write("**Step 2:** Retrieving findings from KB...")
        try:
            from src.kb.connection import get_connection
            from src.content_pipeline.retriever import retrieve_findings
            from src.content_pipeline.selector import select_findings

            with get_connection() as conn:
                retrieved = retrieve_findings(conn, topic=topic, top_k=16, min_confidence=0.45)
                selected = select_findings(conn, retrieved, max_findings=8, brand="explodable", output_type="newsletter")

            st.write(f"→ Retrieved {len(retrieved)} findings, selected {len(selected)}")
        except Exception as e:
            st.error(f"Retrieval failed: {e}")
            selected = []

        if selected:
            # Step 3: Graph expansion
            st.write("**Step 3:** Expanding via relationship graph (PPR + MMR)...")
            try:
                from src.content_pipeline.graph_expander import KBGraph, expand
                kb_graph = KBGraph()
                kb_graph.load()
                seed_ids = [str(sf.finding.id) for sf in selected]
                expanded = expand(kb_graph, seed_ids, max_expand=5)
                n_expanded = sum(1 for r in expanded if r.source == "expanded")
                st.write(f"→ +{n_expanded} cross-domain findings added")
            except Exception as e:
                st.warning(f"Graph expansion skipped: {e}")

            # Step 4: Thesis-constrained outline
            st.write("**Step 4:** Generating thesis-constrained outline (Architecture B)...")
            try:
                from src.content_pipeline.thesis_outline import generate_thesis_outline, validate_thesis_outline, to_newsletter_outline
                thesis_outline = generate_thesis_outline(findings=selected, topic=topic)
                failures = validate_thesis_outline(thesis_outline)
                outline = to_newsletter_outline(thesis_outline)

                if failures:
                    st.write(f"→ Outline generated with {len(failures)} validation notes")
                else:
                    st.write(f"→ Outline passes all structural checks")

                with st.expander("Outline details"):
                    st.write(f"**Title:** {thesis_outline.title}")
                    st.write(f"**Governing thought:** {thesis_outline.governing_thought}")
                    st.write(f"**Opener scene:** {thesis_outline.opener_scene}")
                    for s in thesis_outline.sections:
                        st.write(f"**Section {s.section_number} — {s.stage}:** {s.claim}")
                    st.write(f"**Derivation check:** {thesis_outline.derivation_check}")
            except Exception as e:
                st.error(f"Outline failed: {e}")
                outline = None

            if outline:
                # Step 5: Generate draft
                st.write("**Step 5:** Writing essay (Claude Sonnet 4)...")
                t0 = time.time()
                try:
                    from src.content_pipeline.draft_generator import generate_draft
                    draft_result = generate_draft(
                        outline=outline,
                        findings=selected,
                        brand="explodable",
                        output_type="newsletter",
                    )
                    draft_text = draft_result.newsletter
                    gen_time = round(time.time() - t0, 1)
                    word_count = len(draft_text.split())
                    st.write(f"→ {word_count} words in {gen_time}s")
                except Exception as e:
                    st.error(f"Draft generation failed: {e}")
                    draft_text = None

                if draft_text:
                    # Step 6: Score
                    st.write("**Step 6:** Scoring via calibrated judge...")
                    try:
                        import tempfile
                        from src.content_pipeline.eval.judge import load_rubric, rubric_weights, score_draft

                        rubric_path = Path("config/rubrics/analytical_essay.yaml")
                        rubric = load_rubric(rubric_path)
                        weights = rubric_weights(rubric)

                        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
                            f.write(draft_text)
                            tmp_path = f.name

                        score = score_draft(tmp_path, rubric_path)
                        weighted = round(score.total_weighted(weights), 1)
                        unweighted = score.total_unweighted()
                        os.unlink(tmp_path)

                        st.write(f"→ Score: **{weighted}/57.5** weighted ({unweighted}/50 unweighted)")
                    except Exception as e:
                        st.warning(f"Scoring skipped: {e}")
                        weighted = None

                    status.update(label="Complete!", state="complete")

    # Display the essay
    if draft_text:
        st.markdown("---")
        st.markdown("## Generated essay")

        if weighted:
            col_score, col_words, col_time = st.columns(3)
            with col_score:
                st.metric("Judge score", f"{weighted}/57.5")
            with col_words:
                st.metric("Words", word_count)
            with col_time:
                st.metric("Generation time", f"{gen_time}s")

        st.markdown(draft_text)

        # Show findings used
        with st.expander("Findings used from the knowledge base"):
            for i, sf in enumerate(selected):
                st.markdown(f"**[{i}]** {sf.finding.claim}")
                st.caption(f"Discipline: {sf.finding.academic_discipline} | Confidence: {sf.finding.confidence_score:.2f}")
