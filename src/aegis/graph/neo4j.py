from neo4j import Driver, GraphDatabase

from aegis import config


class CIGClient:
    """Connected Intelligence Graph client for Neo4j."""

    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None) -> None:
        self._driver: Driver = GraphDatabase.driver(
            uri or config.NEO4J_URI,
            auth=(user or config.NEO4J_USER, password or config.NEO4J_PASSWORD),
        )
        self.trace: list[str] = []

    def close(self) -> None:
        self._driver.close()

    def verify_connection(self) -> bool:
        with self._driver.session() as session:
            return session.run("RETURN 1").single()[0] == 1

    def run(self, query: str, **params):
        self.trace.append(query)
        with self._driver.session() as session:
            result = session.run(query, **params)
            return [dict(r) for r in result]
