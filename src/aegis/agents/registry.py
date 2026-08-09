"""CrewAI agent definitions - the six AIDLC roles sharing one local LLM."""

from crewai import Agent

from aegis.llm.crew import build_llm

AGENT_SPECS = [
    dict(
        name="orchestrator",
        role="AEGIS Release Orchestrator",
        goal="Coordinate analyst agents and synthesize their findings into a single, "
             "actionable merge verdict and release recommendation.",
        backstory="Principal release architect for the AIDLC. You weigh deterministic "
                  "graph evidence from the Connected Intelligence Graph against agent "
                  "judgments, then produce a crisp verdict developers can trust.",
    ),
    dict(
        name="pr_reviewer",
        role="PR Compliance Reviewer",
        goal="Verify a pull request's code changes align with the requirements of the "
             "Jira stories it links to, and surface any gaps or scope creep.",
        backstory="Senior code reviewer. You map changed files to story acceptance "
                  "criteria and flag changes that do not belong.",
    ),
    dict(
        name="risk_analyzer",
        role="Risk Analyzer",
        goal="Estimate regression probability and merge confidence from code churn, "
             "test coverage and historical failure data.",
        backstory="Quantitative risk specialist. You translate churn, blast radius and "
                  "past incident signal into numbers: REGRESSION_PROBABILITY and "
                  "MERGE_CONFIDENCE.",
    ),
    dict(
        name="blast_radius",
        role="Blast Radius Analyst",
        goal="Translate graph dependency connections into the concrete set of affected "
             "microservices, API routes and customer-facing flows.",
        backstory="Service topology expert. You read the CIG upstream dependency "
                  "traversal and explain exactly who feels this change.",
    ),
    dict(
        name="test_recommendation",
        role="Test Selector",
        goal="Choose the minimal, targeted set of automated tests to run instead of the "
             "full regression suite.",
        backstory="Test optimization engineer. You prioritize tests by direct file "
                  "coverage, affected-service coverage and regression history, in that "
                  "order, avoiding redundancy.",
    ),
    dict(
        name="deployment_advisor",
        role="Deployment Advisor",
        goal="Assess release readiness by weighing customer impact, open risk and "
             "coverage, then issue a GO or WAIT verdict.",
        backstory="Release manager. You protect the customer experience; you only "
                  "approve deployments that are genuinely safe.",
    ),
]


def build_agents(llm=None) -> dict[str, Agent]:
    llm = llm or build_llm()
    agents = {}
    for spec in AGENT_SPECS:
        agents[spec["name"]] = Agent(
            name=spec["name"],
            role=spec["role"],
            goal=spec["goal"],
            backstory=spec["backstory"],
            llm=llm,
            verbose=False,
            allow_delegation=False,
            max_iter=1,
        )
    return agents
