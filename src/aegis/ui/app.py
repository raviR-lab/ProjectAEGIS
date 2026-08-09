import streamlit as st

from aegis.core.orchestrator import AegisOrchestrator
from aegis.graph.neo4j import CIGClient
from aegis.llm.ollama import OllamaClient

st.set_page_config(page_title="Project AEGIS", layout="wide")

st.title("Project AEGIS")
st.caption("Connected Intelligence Graph (CIG) - AI-driven release shield")

tab_health, tab_analyze = st.tabs(["Infrastructure", "PR Analysis"])

with tab_health:
    with st.spinner("Checking Neo4j connection..."):
        try:
            cig = CIGClient()
            ok = cig.verify_connection()
            cig.close()
            if ok:
                st.success("Neo4j CIG: connected")
            else:
                st.error("Neo4j CIG: connection failed")
        except Exception as exc:
            st.error(f"Neo4j CIG: {exc}")

    with st.spinner("Checking Ollama local LLM..."):
        try:
            llm = OllamaClient()
            models = llm.list_models()
            st.success(f"Ollama: connected - {', '.join(models)}")
            if llm.is_model_available():
                st.info(f"Configured model available: {llm.model}")
            else:
                st.warning(f"Configured model '{llm.model}' not pulled yet")
        except Exception as exc:
            st.error(f"Ollama: {exc}")

with tab_analyze:
    try:
        cig = CIGClient()
        rows = cig.run(
            "MATCH (pr:PullRequest) RETURN pr.number AS number, pr.title AS title "
            "ORDER BY pr.number"
        )
        cig.close()
    except Exception as exc:
        st.error(f"Could not load PRs: {exc}")
        rows = []

    options = {r["number"]: r["title"] for r in rows}
    pr_number = st.selectbox(
        "Pull request",
        list(options.keys()),
        format_func=lambda n: f"#{n} - {options[n]}",
    )

    if st.button("Run AEGIS analysis", type="primary"):
        with st.spinner("Agents reasoning over the CIG (local LLM)..."):
            try:
                report = AegisOrchestrator().analyze_pr(pr_number)
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")
                report = None

        if report:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Verdict", report.verdict)
            col2.metric("Merge confidence", f"{report.merge_confidence:.0f}%")
            col3.metric("Regression probability", f"{report.regression_probability:.0%}")
            col4.metric(
                "Requirement alignment",
                report.agent_outputs.get("alignment", "GAPS"),
            )

            st.subheader("Blast radius")
            st.json(report.blast_radius)

            st.subheader("Recommended tests")
            if report.recommended_tests:
                for test in report.recommended_tests:
                    st.write(f"- {test['id']} ({test['source']})")
            else:
                st.info("No tests in scope.")

            st.subheader("Risk features")
            st.json(report.deterministic_features)

            with st.expander("Raw agent output"):
                st.json(report.agent_outputs)
