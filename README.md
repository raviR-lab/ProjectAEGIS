# PROJECT AEGIS

**AI-driven release shield** — a Connected Intelligence Graph (Neo4j) plus a CrewAI agent crew that answers one question before every merge: **is it safe to ship?**

AEGIS maps your microservice topology, automated tests, incidents and release history into a graph, then reasons over it with local-LLM agents to produce a single actionable verdict per pull request — while telling you exactly which Cypher queries backed the decision.

---

## Why it exists

- **Hidden blast radius.** Changing `payment-svc` silently disturbs `order-svc` and `notification-svc` through dependency edges nobody notices in a diff view.
- **Wasted regression runs.** A full suite of 24 tests to validate 2 files is slow and noisy. AEGIS targets the ~5 tests that actually cover the blast radius.
- **Requirements drift.** PRs quietly touch code unrelated to the Jira story they claim to implement. AEGIS flags those files as misaligned.

The result: **~79% regression-suite cut** for a typical change, while still covering every affected service, route and customer flow.

---

## How it works

```
┌──────────────┐   ┌──────────────────┐   ┌─────────────────────┐   ┌────────────┐
│   CIG        │   │  Deterministic   │   │  CrewAI agents      │   │  Verdict   │
│   (Neo4j)    │──▶│  query layer     │──▶│  (Ollama local LLM) │──▶│ APPROVE /  │
│              │   │  blast_radius    │   │  PR Reviewer        │   │ REVIEW /   │
│ services     │   │  recommended_    │   │  Blast Radius       │   │ REJECT     │
│ files        │   │   tests          │   │  Risk Analyzer      │   │            │
│ tests        │   │  risk_features   │   │  Test Selector      │   │            │
│ routes/flows │   │  story_alignment │   │  Orchestrator       │   │            │
│ incidents    │   │  suite_size      │   │  Deployment Advisor │   │            │
│ releases     │   │  release_history │   └─────────────────────┘   └────────────┘
└──────────────┘   └──────────────────┘
```

1. **CIG (Neo4j)** stores the entity graph (see [Graph schema](#graph-schema)).
2. **The query layer** does all deterministic graph math — blast radius traversal, targeted test selection, risk features, story↔file alignment. Fast, offline, repeatable.
3. **CrewAI agents** add judgment over that evidence using a local Ollama LLM. If the LLM is slow or fails to follow format, the orchestrator **falls back to deterministic math** so the pipeline never bricks.
4. **The orchestrator** assembles an `AegisReport` — verdict, merge confidence, **Risk Score**, blast radius, recommended tests, requirements alignment and full **provenance** (every Cypher query executed).

Two modes:
- **Fast / deterministic** — graph math only. Instant, no LLM needed.
- **Full / agents** — invokes the CrewAI crew over the local LLM for real reasoning.

---

## Architecture (repo layout)

```
aegis/
├── docker-compose.yml          # Neo4j + Ollama + Streamlit app
├── docker/python.Dockerfile    # app image
├── requirements.txt / pyproject.toml
├── scripts/
│   ├── seed_graph.py           # wipe CIG and sync live GitHub PRs + Jira issues
│   └── analyze_pr.py           # CLI: PR analysis / deployment assessment
├── src/aegis/
│   ├── __init__.py             # disables CrewAI telemetry for Streamlit safety
│   ├── config.py               # env-driven config (.env)
│   ├── agents/registry.py      # the seven CrewAI agent role definitions
│   ├── core/orchestrator.py    # AegisReport + deterministic fallbacks + crew wiring
│   ├── graph/
│   │   ├── schema.py           # node labels, relationship types, constraints
│   │   ├── ingest.py           # idempotent MERGE writers for every entity
│   │   ├── queries.py          # blast_radius, recommended_tests, risk_features, …
│   │   └── neo4j.py            # CIGClient (driver + query trace)
│   ├── integrations/           # reserved for GitHub/Jira/Jenkins connectors
│   ├── llm/
│   │   ├── crew.py             # routes every agent to Ollama
│   │   └── ollama.py           # Ollama HTTP client
│   ├── tasks/workflows.py      # CrewAI task definitions (PR + deployment)
│   └── ui/app.py               # Streamlit dashboard
└── tests/                      # unit tests (canned-client, no DB needed)
```

---

## Graph schema

**Node labels**

| Label | Meaning | Key property |
|---|---|---|
| `Microservice` | service, with `domain`, `owner`, `tech` | `name` |
| `CodeFile` | source file owned by a service | `path` |
| `TestCase` | automated test, with `suite`, `test_type`, `tags` | `id` |
| `ApiRoute` | HTTP endpoint (`method` + `path`) | `key` |
| `CustomerFlow` | end-to-end customer journey | `name` |
| `JiraStory` | requirements, with `epic`, `status`, `points` | `key` |
| `Incident` | past failure, with `severity`, `status` | `id` |
| `PullRequest` | change under review, with `author`, `base`, `head` | `number` |
| `Release` | shipped version, with `deployed_at`, `notes` | `version` |

**Relationship types**

| Type | Meaning |
|---|---|
| `BELONGS_TO` | `CodeFile` → `Microservice` |
| `DEPENDS_ON` | consumer → dependency (`order-svc → payment-svc`) |
| `COVERS` | `TestCase` → `CodeFile` |
| `EXPOSES` | `Microservice` → `ApiRoute` |
| `SUPPORTS` | `ApiRoute` → `CustomerFlow` |
| `HAS_INCIDENT` | `Microservice` → `Incident` |
| `DETECTS` | `TestCase` → `Incident` (this test would have caught it) |
| `MODIFIES` | `PullRequest` → `CodeFile` (with `additions`, `deletions`) |
| `ADDRESSES` | `PullRequest` → `JiraStory` |
| `RELEASED_IN` | `Microservice` → `Release` |

Blast radius walks `(upstream)-[:DEPENDS_ON*1..depth]->(changed)` — a change to a dependency propagates **upstream** to its consumers.

---

## Quick start

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env        # then edit NEO4J_PASSWORD / OLLAMA_MODEL
docker compose up -d --build
```

Wait for healthchecks, then sync live GitHub + Jira into the CIG and open the dashboard:

```bash
# inside the app container (or on host if deps installed):
python scripts/seed_graph.py
open http://localhost:8501   # Streamlit dashboard
open http://localhost:7474   # Neo4j Browser
```

### Option B — Local dev

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Neo4j + Ollama via Docker (infra only):
docker compose up -d neo4j ollama

# Wipe the graph and ingest live GitHub PRs + Jira issues:
python scripts/seed_graph.py
streamlit run src/aegis/ui/app.py
```

Re-run `scripts/seed_graph.py` any time to wipe synthetic leftovers and refresh from GitHub and Jira.

---

## Running analyses

### Streamlit dashboard

Open `http://localhost:8501`:

- **Infrastructure & CIG** — stack status, graph intelligence (node/relationship counts), open incidents, release timeline, and the seven CrewAI agents.
- **PR Analysis** — pick a PR, toggle **Fast mode** (deterministic, instant) or let the agents reason over the local LLM, then inspect:
  - agent output diagram (each agent's verdict line)
  - final verdict + merge confidence + **Risk Score**
  - requirements alignment (green ✓ / red ✗ per changed file vs. linked story epic)
  - blast chain (hop-distance through the dependency graph)
  - targeted test set with the suite-cut metric
  - **data provenance** — every Cypher query AEGIS executed, plus graph entity counts

### CLI

```bash
python scripts/analyze_pr.py --pr 1              # full agent analysis
python scripts/analyze_pr.py --pr 1 --fast       # deterministic only
python scripts/analyze_pr.py --deploy v1.11.0 --services payment-svc
```

### Demo data (live GitHub + Jira)

The CIG is **not** preloaded with fake PRs. `scripts/seed_graph.py` wipes Neo4j and ingests:

- GitHub pull requests and changed files from `GITHUB_REPO_OWNER/GITHUB_REPO_NAME`
- Jira issues from `JIRA_PROJECT_KEY`
- Microservices inferred from file paths (`payment-svc/…`, `auth-svc/…`)

On [dummy-ecommerce](https://github.com/rizwanrnt/dummy-ecommerce/pulls):

| PR | Jira | Change | Alignment |
|---|---|---|---|
| #1 | **AEG-4** Payments | `payment-svc` refund/gateway | **ALIGNED** — files match the ticket |
| #2 | **AEG-1** (if cited) | `auth-svc` key rotation | isolated auth change |
| #3 | **AEG-5** Platform / admin dark mode | `payment-svc/src/charge.ts` | **GAPS / REJECT** — admin ticket, payments code |

---

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt endpoint |
| `NEO4J_USER` | `neo4j` | Neo4j user |
| `NEO4J_PASSWORD` | `changeme` | Neo4j password |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local LLM endpoint |
| `OLLAMA_MODEL` | `LFM2.5:Q4` | Model used by every agent |
| `GITHUB_*`, `JIRA_*`, `JENKINS_*` | — | Reserved for integration connectors |

---

## Tests

```bash
python -m unittest discover -s tests -v
```

The query-layer tests run against a canned client (no live DB); Cypher execution itself is validated by `scripts/seed_graph.py` against live GitHub and Jira once the stack is up.

---

## Exploring the CIG in Neo4j Browser

Open `http://localhost:7474` and try:

```cypher
MATCH (n) RETURN n                                          // everything, color-coded
MATCH (ms:Microservice)-[d:DEPENDS_ON]->(dep) RETURN ms, d, dep   // dependency graph
MATCH p=(pr:PullRequest {number:1})-[:MODIFIES]->(:CodeFile)-[:BELONGS_TO]->(:Microservice) RETURN p
MATCH (pr:PullRequest)-[:ADDRESSES]->(s:JiraStory) RETURN pr.number, pr.title, s.key, s.epic
```

Every query the dashboard runs is printed verbatim in its **Data provenance** panel — copy any of them straight into Neo4j Browser.
