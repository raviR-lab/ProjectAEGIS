"""AegisOrchestrator - coordinates the CrewAI agents over the CIG.

The graph does the deterministic work (blast radius, test selection, risk
features); the local LLM adds judgment. The orchestrator parses agent
outputs and falls back to deterministic math when the LLM is verbose or
fails to follow format, so the pipeline never bricks on a chatty model.
"""

import json
import re
from dataclasses import dataclass, field

from crewai import Crew

from aegis.agents.registry import build_agents
from aegis.graph import queries
from aegis.graph.neo4j import CIGClient
from aegis.llm.crew import build_llm
from aegis.tasks.workflows import build_deployment_tasks, build_pr_tasks

ROLE_ORCHESTRATOR = "AEGIS Release Orchestrator"
ROLE_PR_REVIEWER = "PR Compliance Reviewer"
ROLE_RISK_ANALYZER = "Risk Analyzer"
ROLE_DEPLOYMENT_ADVISOR = "Deployment Advisor"


@dataclass
class AegisReport:
    pr_number: int | None = None
    verdict: str = "UNKNOWN"
    merge_confidence: float = 0.0
    regression_probability: float = 0.0
    deterministic_features: dict = field(default_factory=dict)
    blast_radius: dict = field(default_factory=dict)
    recommended_tests: list = field(default_factory=list)
    agent_outputs: dict = field(default_factory=dict)


def _extract_number(text: str, label: str, fallback: float | None) -> float | None:
    pattern = re.compile(rf"{label}\s*[:=]?\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
    match = pattern.search(text or "")
    if match:
        value = float(match.group(1))
        return max(0.0, min(1.0, value)) if label.lower().endswith("probability") else value
    return fallback


def deterministic_regression(features: dict) -> float:
    """Fallback regression probability from graph features alone."""
    p = 0.0
    p += min(0.15, features.get("churn", 0) / 1000.0)
    p += 0.10 * max(0, features.get("num_affected_services", 1) - 1)
    p += 0.15 * len(features.get("past_incidents", []))
    p += 0.10 if features.get("affected_flows") else 0.0
    if features.get("file_test_coverage_ratio", 0.0) >= 1.0:
        p -= 0.05
    return max(0.05, min(0.95, p))


class AegisOrchestrator:
    def __init__(self, cig: CIGClient | None = None, *, llm=None) -> None:
        self.cig = cig or CIGClient()
        self.llm = llm or build_llm()
        self.agents = build_agents(self.llm)

    def _gather_pr_context(self, pr_number: int) -> dict:
        rows = self.cig.run(
            """
            MATCH (pr:PullRequest {number: $number})
            OPTIONAL MATCH (pr)-[:ADDRESSES]->(s:JiraStory)
            RETURN pr.title AS title, pr.author AS author, pr.state AS state,
                   pr.base AS base, pr.head AS head,
                   collect(DISTINCT {key: s.key, title: s.title, status: s.status}) AS stories
            """,
            number=pr_number,
        )
        pr_row = rows[0] if rows else {}
        files = queries._pr_files(self.cig, pr_number)
        radius = queries.blast_radius(self.cig, pr_number)
        features = queries.risk_features(self.cig, pr_number)
        tests = queries.recommended_tests(self.cig, pr_number)
        return {
            "pr": {
                "number": pr_number,
                "title": pr_row.get("title", "untitled"),
                "author": pr_row.get("author", "unknown"),
                "state": pr_row.get("state", "open"),
                "base": pr_row.get("base", "main"),
                "head": pr_row.get("head", ""),
            },
            "stories": [s for s in pr_row.get("stories", []) if s.get("key")],
            "files": files,
            "blast_radius": radius,
            "risk_features": features,
            "recommended_tests": tests,
        }

    def _parse_pr_outputs(self, context: dict, tasks) -> dict:
        raw = {t.agent.role: t.output.raw if t.output else "" for t in tasks}
        risk_raw = raw.get(ROLE_RISK_ANALYZER, "")
        llm_regression = _extract_number(risk_raw, "REGRESSION_PROBABILITY", None)
        llm_confidence = _extract_number(risk_raw, "MERGE_CONFIDENCE", None)

        features = context["risk_features"]
        deterministic = deterministic_regression(features)
        regression = (
            0.6 * llm_regression + 0.4 * deterministic
            if llm_regression is not None
            else deterministic
        )
        confidence = llm_confidence if llm_confidence is not None else 100.0 * (1 - regression)
        confidence = max(5.0, min(95.0, confidence))

        alignment_raw = raw.get(ROLE_PR_REVIEWER, "")
        alignment = "ALIGNED" if "ALIGNED" in alignment_raw.upper() else "GAPS"

        synthesis_raw = raw.get(ROLE_ORCHESTRATOR, "")
        upper = synthesis_raw.upper()
        if "REJECT" in upper:
            verdict = "REJECT"
        elif "REVIEW" in upper:
            verdict = "REVIEW"
        elif "APPROVE" in upper:
            verdict = "APPROVE"
        else:
            verdict = "REVIEW"

        return {
            "raw": raw,
            "alignment": alignment,
            "llm_regression_probability": llm_regression,
            "regression_probability": round(regression, 3),
            "merge_confidence": round(confidence, 1),
            "verdict": verdict,
        }

    def analyze_pr(self, pr_number: int, *, verbose: bool = False) -> AegisReport:
        context = self._gather_pr_context(pr_number)
        tasks = build_pr_tasks(self.agents, context)
        crew = Crew(
            agents=list(self.agents.values()),
            tasks=tasks,
            verbose=verbose,
            tracing=False,
        )
        crew.kickoff()
        parsed = self._parse_pr_outputs(context, tasks)

        return AegisReport(
            pr_number=pr_number,
            verdict=parsed["verdict"],
            merge_confidence=parsed["merge_confidence"],
            regression_probability=parsed["regression_probability"],
            deterministic_features=context["risk_features"],
            blast_radius=context["blast_radius"],
            recommended_tests=context["recommended_tests"],
            agent_outputs={
                "alignment": parsed["alignment"],
                "llm_regression_probability": parsed["llm_regression_probability"],
                "raw": parsed["raw"],
            },
        )

    def assess_deployment(self, version: str, services: list[str],
                          *, verbose: bool = False) -> dict:
        features = {
            "services": services,
            "num_affected_services": len(services),
        }
        incidents = []
        if services:
            rows = self.cig.run(
                """
                MATCH (ms:Microservice)-[:HAS_INCIDENT]->(inc:Incident)
                WHERE ms.name IN $services AND inc.status <> 'resolved'
                RETURN collect(DISTINCT inc.id) AS open_incidents
                """,
                services=services,
            )
            incidents = rows[0]["open_incidents"] if rows else []

        context = {
            "version": version,
            "services": ", ".join(services),
            "features": json.dumps(features, indent=2),
            "incidents": incidents,
            "num_changes": len(services),
        }
        tasks = build_deployment_tasks(self.agents, context)
        crew = Crew(
            agents=[self.agents["risk_analyzer"], self.agents["deployment_advisor"]],
            tasks=tasks,
            verbose=verbose,
            tracing=False,
        )
        crew.kickoff()

        raw = {t.agent.role: t.output.raw if t.output else "" for t in tasks}
        advisor_raw = raw.get(ROLE_DEPLOYMENT_ADVISOR, "")
        decision = "GO" if "DEPLOYMENT=GO" in advisor_raw.upper() else "WAIT"
        readiness = _extract_number(
            raw.get(ROLE_RISK_ANALYZER, ""), "RELEASE_READINESS",
            max(5.0, min(95.0, 100 * (1 - deterministic_regression(features)))),
        )
        return {
            "version": version,
            "services": services,
            "open_incidents": incidents,
            "release_readiness": round(readiness, 1),
            "decision": decision,
            "reason": advisor_raw,
        }


def format_report(report: AegisReport) -> str:
    return json.dumps(
        {
            "pr_number": report.pr_number,
            "verdict": report.verdict,
            "merge_confidence": report.merge_confidence,
            "regression_probability": report.regression_probability,
            "recommended_tests": [t["id"] for t in report.recommended_tests],
            "affected_services": report.blast_radius.get("affected_services", []),
            "affected_flows": report.deterministic_features.get("affected_flows", []),
            "past_incidents": report.deterministic_features.get("past_incidents", []),
            "agent_alignment": report.agent_outputs.get("alignment"),
        },
        indent=2,
        default=str,
    )
