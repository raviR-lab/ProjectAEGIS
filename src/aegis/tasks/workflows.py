"""CrewAI task definitions for the PR and Deployment stages."""

import json

from crewai import Task


def _fmt(obj) -> str:
    return json.dumps(obj, indent=2, default=str)


def build_pr_tasks(agents: dict[str, object], context: dict) -> list[Task]:
    """Five sequential tasks: review, blast, risk, test selection, synthesis."""
    pr = context["pr"]
    files = context["files"]
    radius = context["blast_radius"]
    features = context["risk_features"]
    tests = context["recommended_tests"]
    stories = context["stories"]

    t_review = Task(
        description=(
            "Pull request #%(number)d '%(title)s' by %(author)s touches these files:\n"
            "%(files)s\n\n"
            "Linked Jira stories:\n%(stories)s\n\n"
            "Assess whether each changed file serves the linked stories' intent. "
            "List any file that appears unrelated to the stories."
        ) % {"number": pr["number"], "title": pr["title"], "author": pr["author"],
             "files": _fmt(files), "stories": _fmt(stories)},
        expected_output=(
            "Verdict line 'ALIGNMENT=ALIGNED' or 'ALIGNMENT=GAPS' followed by a short "
            "list of unrelated files or missing-requirement gaps."
        ),
        agent=agents["pr_reviewer"],
        async_execution=True,
    )

    t_blast = Task(
        description=(
            "The CIG upstream traversal for PR #%(number)d produced this blast radius:\n"
            "%(radius)s\n\n"
            "Explain in plain terms which microservices, API routes and customer-facing "
            "flows are affected, and by how many dependency hops."
        ) % {"number": pr["number"], "radius": _fmt(radius)},
        expected_output=(
            "Summary line 'AFFECTED=<count>' followed by bullet points naming the "
            "affected services, routes and flows."
        ),
        agent=agents["blast_radius"],
        async_execution=True,
    )

    t_risk = Task(
        description=(
            "Compute regression risk for PR #%(number)d from these deterministic features:\n"
            "%(features)s\n\n"
            "Return the two required numbers plus a one-sentence reason."
        ) % {"number": pr["number"], "features": _fmt(features)},
        expected_output=(
            "Output exactly these lines:\n"
            "REGRESSION_PROBABILITY=<number between 0 and 1>\n"
            "MERGE_CONFIDENCE=<number between 0 and 100>\n"
            "REASON=<one sentence>"
        ),
        agent=agents["risk_analyzer"],
        async_execution=True,
    )

    t_test = Task(
        description=(
            "Select the final ordered test set for PR #%(number)d from these candidates "
            "(already prioritized by source):\n%(tests)s\n\n"
            "Return the test ids in the order they should run. Skip redundant entries "
            "already implied by a higher-priority source."
        ) % {"number": pr["number"], "tests": _fmt(tests)},
        expected_output="One test id per line, in execution order.",
        agent=agents["test_recommendation"],
        async_execution=True,
    )

    t_synthesis = Task(
        description=(
            "Synthesize the four analyst reports into a final verdict for PR #%(number)d. "
            "The PR changes: %(files)s"
        ) % {"number": pr["number"], "files": _fmt(files)},
        expected_output=(
            "Final line 'VERDICT=APPROVE' | 'VERDICT=REVIEW' | 'VERDICT=REJECT', then a "
            "two-sentence summary the developer can act on."
        ),
        agent=agents["orchestrator"],
        context=[t_review, t_blast, t_risk, t_test],
    )

    return [t_review, t_blast, t_risk, t_test, t_synthesis]


def build_deployment_tasks(agents: dict[str, object], context: dict) -> list[Task]:
    """Deployment readiness: risk + test coverage + customer impact -> GO/WAIT."""
    t_risk = Task(
        description=(
            "Release '%(version)s' affects services: %(services)s.\n"
            "Aggregated risk features:\n%(features)s\n\n"
            "Assess deployment readiness."
        ) % context,
        expected_output=(
            "Output exactly these lines:\n"
            "REGRESSION_PROBABILITY=<number between 0 and 1>\n"
            "RELEASE_READINESS=<number between 0 and 100>"
        ),
        agent=agents["risk_analyzer"],
    )

    t_advisor = Task(
        description=(
            "Release '%(version)s' covers %(num_changes)d changes across services "
            "%(services)s. Open incidents in scope: %(incidents)s. Regression "
            "probability assessed by the risk analyst.\n\n"
            "Decide GO or WAIT and justify briefly."
        ) % context,
        expected_output=(
            "Final line 'DEPLOYMENT=GO' or 'DEPLOYMENT=WAIT', then a one-sentence reason."
        ),
        agent=agents["deployment_advisor"],
        context=[t_risk],
    )

    return [t_risk, t_advisor]
