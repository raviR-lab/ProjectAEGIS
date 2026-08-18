"""Query layer - blast radius, test recommendation and risk features for a PR.

All analyses are read-only traversals over the CIG. They produce the JSON
context that the CrewAI agents (Risk Analyzer, Blast Radius, Security, Test
Recommendation) consume in the next iteration.
"""

import collections

from aegis.graph import schema


def _pr_files(cig, pr_number: int) -> list[dict]:
    rows = cig.run(
        f"""
        MATCH (pr:{schema.PULL_REQUEST} {{number: $number}})-[m:{schema.MODIFIES}]->(f:{schema.CODE_FILE})
        OPTIONAL MATCH (f)-[:{schema.BELONGS_TO}]->(ms:{schema.MICROSERVICE})
        OPTIONAL MATCH (t:{schema.TEST_CASE})-[:{schema.COVERS}]->(f)
        RETURN f.path AS path, m.additions AS additions, m.deletions AS deletions,
               ms.name AS microservice, collect(DISTINCT t.id) AS covered_by_tests
        """,
        number=pr_number,
    )
    return [dict(r) for r in rows]


def blast_radius(cig, pr_number: int, *, max_depth: int = 3) -> dict:
    """Map every entity a PR can disturb: services, routes, flows, incidents.

    `DEPENDS_ON` points from a consumer to its dependency. A change in a
    dependency propagates *upstream* to its consumers, so we walk
    ``(upstream)-[:DEPENDS_ON*1..depth]->(changed)``.
    """
    files = _pr_files(cig, pr_number)
    changed_services = sorted({f["microservice"] for f in files if f["microservice"]})

    depth = int(max_depth)
    depth_pattern = "-[:%s*1..%d]->" % (schema.DEPENDS_ON, depth)

    affected_rows = cig.run(
        f"""
        MATCH (changed:{schema.MICROSERVICE})
        WHERE changed.name IN $changed_services
        MATCH p = (upstream:{schema.MICROSERVICE}){depth_pattern}(changed)
        RETURN DISTINCT upstream.name AS service, length(p) AS hops
        """,
        changed_services=changed_services,
    )
    affected = collections.defaultdict(set)
    for r in affected_rows:
        affected[r["service"]].add(r["hops"])
    upstream = sorted(affected)
    all_services = sorted(set(changed_services) | set(upstream))

    detail_rows = cig.run(
        f"""
        MATCH (ms:{schema.MICROSERVICE})
        WHERE ms.name IN $all_services
        OPTIONAL MATCH (ms)-[:{schema.EXPOSES}]->(r:{schema.API_ROUTE})
        OPTIONAL MATCH (r)-[:{schema.SUPPORTS}]->(f:{schema.CUSTOMER_FLOW})
        OPTIONAL MATCH (ms)-[:{schema.HAS_INCIDENT}]->(inc:{schema.INCIDENT})
        OPTIONAL MATCH (t:{schema.TEST_CASE})-[:{schema.COVERS}]->(cf:{schema.CODE_FILE})-[:{schema.BELONGS_TO}]->(ms)
        RETURN ms.name AS service,
               collect(DISTINCT r.key) AS routes,
               collect(DISTINCT f.name) AS flows,
               collect(DISTINCT inc.id) AS incidents,
               collect(DISTINCT t.id) AS tests
        """,
        all_services=all_services,
    )
    services_detail = {r["service"]: r for r in detail_rows}

    return {
        "pr_number": pr_number,
        "files": files,
        "changed_services": changed_services,
        "affected_services": all_services,
        "upstream_hops": {k: sorted(v) for k, v in affected.items()},
        "services_detail": services_detail,
    }


def recommended_tests(cig, pr_number: int, *, max_depth: int = 3) -> list[dict]:
    """Select the minimal targeted test set for a PR.

    Sources, in priority order:
      1. Tests directly covering modified files.
      2. Tests covering files owned by any affected (changed + upstream) service.
      3. Tests that have detected past incidents in affected services.
    """
    radius = blast_radius(cig, pr_number, max_depth=max_depth)
    all_services = radius["affected_services"]

    direct = {
        t for f in radius["files"] for t in f["covered_by_tests"]
    }

    service_tests = {
        t
        for detail in radius["services_detail"].values()
        for t in detail["tests"]
    }

    regression_rows = cig.run(
        f"""
        MATCH (ms:{schema.MICROSERVICE})-[:{schema.HAS_INCIDENT}]->(inc:{schema.INCIDENT})
        MATCH (t:{schema.TEST_CASE})-[:{schema.DETECTS}]->(inc)
        WHERE ms.name IN $all_services
        RETURN DISTINCT t.id AS id, t.name AS name, t.suite AS suite,
                        t.test_type AS type, t.avg_duration_s AS duration,
                        collect(DISTINCT inc.id) AS incident_ids
        """,
        all_services=all_services,
    )
    regression = {r["id"] for r in regression_rows}

    prioritized: list[dict] = []
    seen: set[str] = set()

    def add(id: str, source: str, extra: dict | None = None):
        if id in seen:
            return
        seen.add(id)
        prioritized.append({"id": id, "source": source, **(extra or {})})

    for t in sorted(direct):
        add(t, "direct_file_coverage")
    for t in sorted(service_tests - direct):
        add(t, "affected_service_coverage")
    for r in regression_rows:
        row = dict(r)
        add(row["id"], "regression_history", {"incidents": row["incident_ids"]})

    return prioritized


def risk_features(cig, pr_number: int, *, max_depth: int = 3) -> dict:
    """Numerical features consumed by the Risk Analyzer agent."""
    radius = blast_radius(cig, pr_number, max_depth=max_depth)
    files = radius["files"]
    affected_services = radius["affected_services"]

    totals = {"additions": 0, "deletions": 0}
    for f in files:
        totals["additions"] += f["additions"] or 0
        totals["deletions"] += f["deletions"] or 0

    incidents = {
        inc
        for d in radius["services_detail"].values()
        for inc in d["incidents"]
        if inc
    }

    # Only *resolved* incidents count as regression history. Open incidents are
    # current problems handled by deployment readiness, not past signal.
    resolved_rows = cig.run(
        f"""
        MATCH (ms:{schema.MICROSERVICE})-[:{schema.HAS_INCIDENT}]->(inc:{schema.INCIDENT})
        WHERE ms.name IN $affected_services AND inc.status = 'resolved'
        RETURN collect(DISTINCT inc.id) AS resolved
        """,
        affected_services=affected_services,
    )
    resolved = set(resolved_rows[0]["resolved"]) if resolved_rows else set()
    past = incidents & resolved

    return {
        "pr_number": pr_number,
        "num_files": len(files),
        "additions": totals["additions"],
        "deletions": totals["deletions"],
        "churn": totals["additions"] + totals["deletions"],
        "changed_services": radius["changed_services"],
        "num_affected_services": len(affected_services),
        "num_affected_routes": sum(
            1 for d in radius["services_detail"].values() if d["routes"]
        ),
        "affected_flows": sorted(
            {
                flow
                for d in radius["services_detail"].values()
                for flow in d["flows"]
            }
        ),
        "past_incidents": sorted(past),
        "file_test_coverage_ratio": sum(
            1 for f in files if f["covered_by_tests"]
        ) / max(len(files), 1),
    }


def story_alignment(cig, pr_number: int) -> dict:
    """Map each changed file to its linked Jira story.

    A file is "aligned" when its microservice domain matches the epic of at
    least one linked story. Deterministic — no LLM needed — so the reviewer
    agent can be verified against it and the demo always renders.
    """
    story_rows = cig.run(
        f"""
        MATCH (pr:{schema.PULL_REQUEST} {{number: $number}})-[:{schema.ADDRESSES}]->(s:{schema.JIRA_STORY})
        RETURN collect(DISTINCT {{key: s.key, title: s.title, epic: s.epic, status: s.status}}) AS stories
        """,
        number=pr_number,
    )
    stories = story_rows[0]["stories"] if story_rows else []
    stories = [s for s in stories if s.get("key")]
    epics = {str(s.get("epic") or "").strip().lower() for s in stories}

    file_rows = cig.run(
        f"""
        MATCH (pr:{schema.PULL_REQUEST} {{number: $number}})-[:{schema.MODIFIES}]->(f:{schema.CODE_FILE})
        OPTIONAL MATCH (f)-[:{schema.BELONGS_TO}]->(ms:{schema.MICROSERVICE})
        RETURN f.path AS path, ms.name AS microservice, ms.domain AS domain
        """,
        number=pr_number,
    )

    files = []
    for r in file_rows:
        domain = (r["domain"] or "").strip().lower()
        aligned = bool(epics) and domain in epics
        files.append({
            "path": r["path"],
            "microservice": r["microservice"],
            "domain": r["domain"] or "unknown",
            "aligned": aligned,
            "reason": "no linked story" if not epics else
                      f"service domain '{r['domain']}' matches story epic" if aligned else
                      f"service domain '{r['domain']}' does not match any story epic",
        })

    return {
        "pr_number": pr_number,
        "linked_stories": stories,
        "files": files,
        "alignment": "ALIGNED" if files and all(f["aligned"] for f in files) else "GAPS",
    }


def suite_size(cig) -> int:
    rows = cig.run(f"MATCH (t:{schema.TEST_CASE}) RETURN count(t) AS total")
    return rows[0]["total"] if rows else 0


def release_history(cig) -> list[dict]:
    rows = cig.run(
        f"""
        MATCH (r:{schema.RELEASE})
        OPTIONAL MATCH (ms:{schema.MICROSERVICE})-[:{schema.RELEASED_IN}]->(r)
        RETURN r.version AS version, r.deployed_at AS deployed_at, r.status AS status,
               r.notes AS notes, collect(DISTINCT ms.name) AS services
        ORDER BY r.deployed_at
        """
    )
    return [dict(r) for r in rows]


def open_incidents(cig) -> list[dict]:
    rows = cig.run(
        f"""
        MATCH (ms:{schema.MICROSERVICE})-[:{schema.HAS_INCIDENT}]->(inc:{schema.INCIDENT})
        WHERE inc.status = 'open'
        RETURN inc.id AS id, inc.severity AS severity, inc.root_cause AS root_cause,
               ms.name AS service
        """
    )
    return [dict(r) for r in rows]


def graph_stats(cig) -> dict:
    node_rows = cig.run(
        "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count"
    )
    nodes = {r["label"]: r["count"] for r in node_rows}
    rel_rows = cig.run(
        "MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS count"
    )
    rels = {r["rel"]: r["count"] for r in rel_rows}
    return {"nodes": nodes, "relationships": rels}
