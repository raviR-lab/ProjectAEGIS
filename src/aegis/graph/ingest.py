"""Ingestion layer - idempotent MERGE-based writers for every CIG entity."""

from aegis.graph import schema


def ingest_microservice(cig, name: str, *, domain: str | None = None,
                        owner: str | None = None, tech: str | None = None) -> None:
    cig.run(
        f"MERGE (ms:{schema.MICROSERVICE} {{name: $name}}) "
        "SET ms.domain = COALESCE($domain, ms.domain), "
        "    ms.owner = COALESCE($owner, ms.owner), "
        "    ms.tech = COALESCE($tech, ms.tech)",
        name=name, domain=domain, owner=owner, tech=tech,
    )


def ingest_dependency(cig, consumer: str, dependency: str) -> None:
    cig.run(
        f"MATCH (a:{schema.MICROSERVICE} {{name: $consumer}}), "
        f"(b:{schema.MICROSERVICE} {{name: $dependency}}) "
        f"MERGE (a)-[:{schema.DEPENDS_ON}]->(b)",
        consumer=consumer, dependency=dependency,
    )


def ingest_code_file(cig, path: str, *, language: str | None = None,
                     microservice: str | None = None) -> None:
    cig.run(
        f"MERGE (f:{schema.CODE_FILE} {{path: $path}}) "
        "SET f.language = COALESCE($language, f.language)",
        path=path, language=language,
    )
    if microservice:
        cig.run(
            f"MATCH (f:{schema.CODE_FILE} {{path: $path}}), "
            f"(ms:{schema.MICROSERVICE} {{name: $microservice}}) "
            f"MERGE (f)-[:{schema.BELONGS_TO}]->(ms)",
            path=path, microservice=microservice,
        )


def reset_graph(cig) -> None:
    """Drop every node/relationship, then reinstall uniqueness constraints."""
    cig.run("MATCH (n) DETACH DELETE n")
    schema.install_schema(cig)


def ingest_jira_story(cig, key: str, title: str, *, status: str | None = None,
                      points: int | None = None, epic: str | None = None) -> None:
    cig.run(
        f"MERGE (s:{schema.JIRA_STORY} {{key: $key}}) "
        "SET s.title = COALESCE($title, s.title), "
        "    s.status = COALESCE($status, s.status), "
        "    s.points = COALESCE($points, s.points), "
        "    s.epic = COALESCE($epic, s.epic)",
        key=key, title=title, status=status, points=points, epic=epic,
    )


def ingest_pull_request(cig, number: int, title: str, author: str, *, base: str,
                        head: str, state: str = "open") -> None:
    cig.run(
        f"MERGE (pr:{schema.PULL_REQUEST} {{number: $number}}) "
        "SET pr.title = $title, "
        "    pr.author = COALESCE($author, pr.author), "
        "    pr.base = COALESCE($base, pr.base), "
        "    pr.head = COALESCE($head, pr.head), "
        "    pr.state = COALESCE($state, pr.state)",
        number=number, title=title, author=author, base=base, head=head, state=state,
    )


def ingest_pr_changes(cig, pr_number: int, changes: list[dict]) -> None:
    """Link a PR to the files it modifies.

    changes: [{path, additions, deletions}]
    """
    for change in changes:
        cig.run(
            f"MATCH (pr:{schema.PULL_REQUEST} {{number: $number}}), "
            f"(f:{schema.CODE_FILE} {{path: $path}}) "
            f"MERGE (pr)-[r:{schema.MODIFIES}]->(f) "
            "SET r.additions = $additions, r.deletions = $deletions",
            number=pr_number, path=change["path"],
            additions=change.get("additions", 0), deletions=change.get("deletions", 0),
        )


def replace_pr_changes(cig, pr_number: int, changes: list[dict]) -> None:
    """Drop previous MODIFIES edges, then write the live GitHub file list."""
    cig.run(
        f"MATCH (pr:{schema.PULL_REQUEST} {{number: $number}})"
        f"-[r:{schema.MODIFIES}]->(:{schema.CODE_FILE}) DELETE r",
        number=pr_number,
    )
    ingest_pr_changes(cig, pr_number, changes)


def link_pr_to_story(cig, pr_number: int, story_key: str) -> None:
    cig.run(
        f"MATCH (pr:{schema.PULL_REQUEST} {{number: $number}}), "
        f"(s:{schema.JIRA_STORY} {{key: $key}}) "
        f"MERGE (pr)-[:{schema.ADDRESSES}]->(s)",
        number=pr_number, key=story_key,
    )


def unlink_pr_stories(cig, pr_number: int) -> None:
    cig.run(
        f"MATCH (pr:{schema.PULL_REQUEST} {{number: $number}})"
        f"-[r:{schema.ADDRESSES}]->(:{schema.JIRA_STORY}) DELETE r",
        number=pr_number,
    )


def relink_pr_to_story(cig, pr_number: int, story_key: str) -> None:
    """Replace every ADDRESSES edge on the PR with a single story."""
    unlink_pr_stories(cig, pr_number)
    link_pr_to_story(cig, pr_number, story_key)


def ingest_api_route(cig, microservice: str, method: str, path: str) -> None:
    key = f"{method} {path}"
    cig.run(
        f"MERGE (r:{schema.API_ROUTE} {{key: $key}}) "
        "SET r.method = $method, r.path = $path",
        key=key, method=method, path=path,
    )
    cig.run(
        f"MATCH (ms:{schema.MICROSERVICE} {{name: $microservice}}), "
        f"(r:{schema.API_ROUTE} {{key: $key}}) "
        f"MERGE (ms)-[:{schema.EXPOSES}]->(r)",
        microservice=microservice, key=key,
    )


def ingest_customer_flow(cig, name: str, description: str, *routes: tuple[str, str]) -> None:
    cig.run(
        f"MERGE (f:{schema.CUSTOMER_FLOW} {{name: $name}}) "
        "SET f.description = COALESCE($description, f.description)",
        name=name, description=description,
    )
    for method, path in routes:
        cig.run(
            f"MATCH (f:{schema.CUSTOMER_FLOW} {{name: $name}}), "
            f"(r:{schema.API_ROUTE} {{key: $key}}) "
            f"MERGE (r)-[:{schema.SUPPORTS}]->(f)",
            name=name, key=f"{method} {path}",
        )


def ingest_test_case(cig, id: str, name: str, *, suite: str, test_type: str,
                     tags: str | None = None, avg_duration_s: float = 0.0) -> None:
    cig.run(
        f"MERGE (t:{schema.TEST_CASE} {{id: $id}}) "
        "SET t.name = COALESCE($name, t.name), "
        "    t.suite = COALESCE($suite, t.suite), "
        "    t.test_type = COALESCE($test_type, t.test_type), "
        "    t.tags = COALESCE($tags, t.tags), "
        "    t.avg_duration_s = COALESCE($avg_duration_s, t.avg_duration_s)",
        id=id, name=name, suite=suite, test_type=test_type,
        tags=tags, avg_duration_s=avg_duration_s,
    )


def link_test_coverage(cig, test_id: str, file_path: str) -> None:
    cig.run(
        f"MATCH (t:{schema.TEST_CASE} {{id: $test_id}}), "
        f"(f:{schema.CODE_FILE} {{path: $file_path}}) "
        f"MERGE (t)-[:{schema.COVERS}]->(f)",
        test_id=test_id, file_path=file_path,
    )


def ingest_incident(cig, id: str, severity: str, *, status: str,
                    root_cause: str | None = None, microservice: str | None = None,
                    detected_by_test: str | None = None) -> None:
    cig.run(
        f"MERGE (inc:{schema.INCIDENT} {{id: $id}}) "
        "SET inc.severity = COALESCE($severity, inc.severity), "
        "    inc.status = COALESCE($status, inc.status), "
        "    inc.root_cause = COALESCE($root_cause, inc.root_cause)",
        id=id, severity=severity, status=status, root_cause=root_cause,
    )
    if microservice:
        cig.run(
            f"MATCH (ms:{schema.MICROSERVICE} {{name: $microservice}}), "
            f"(inc:{schema.INCIDENT} {{id: $id}}) "
            f"MERGE (ms)-[:{schema.HAS_INCIDENT}]->(inc)",
            microservice=microservice, id=id,
        )
    if detected_by_test:
        cig.run(
            f"MATCH (t:{schema.TEST_CASE} {{id: $test_id}}), "
            f"(inc:{schema.INCIDENT} {{id: $id}}) "
            f"MERGE (t)-[:{schema.DETECTS}]->(inc)",
            test_id=detected_by_test, id=id,
        )


def ingest_release(cig, version: str, *, deployed_at: str | None = None,
                   status: str | None = None, notes: str | None = None) -> None:
    cig.run(
        f"MERGE (r:{schema.RELEASE} {{version: $version}}) "
        "SET r.deployed_at = COALESCE($deployed_at, r.deployed_at), "
        "    r.status = COALESCE($status, r.status), "
        "    r.notes = COALESCE($notes, r.notes)",
        version=version, deployed_at=deployed_at, status=status, notes=notes,
    )


def link_service_release(cig, microservice: str, version: str) -> None:
    cig.run(
        f"MATCH (ms:{schema.MICROSERVICE} {{name: $microservice}}), "
        f"(r:{schema.RELEASE} {{version: $version}}) "
        f"MERGE (ms)-[:{schema.RELEASED_IN}]->(r)",
        microservice=microservice, version=version,
    )
