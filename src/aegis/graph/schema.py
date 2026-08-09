"""Connected Intelligence Graph (CIG) - schema, node labels and relationship types."""

# --- Node labels ---
PULL_REQUEST = "PullRequest"
CODE_FILE = "CodeFile"
MICROSERVICE = "Microservice"
JIRA_STORY = "JiraStory"
TEST_CASE = "TestCase"
API_ROUTE = "ApiRoute"
CUSTOMER_FLOW = "CustomerFlow"
INCIDENT = "Incident"
RELEASE = "Release"

# --- Relationship types ---
MODIFIES = "MODIFIES"
BELONGS_TO = "BELONGS_TO"
DEPENDS_ON = "DEPENDS_ON"
ADDRESSES = "ADDRESSES"
COVERS = "COVERS"
EXPOSES = "EXPOSES"
SUPPORTS = "SUPPORTS"
HAS_INCIDENT = "HAS_INCIDENT"
DETECTS = "DETECTS"
RELEASED_IN = "RELEASED_IN"

# Unique constraint / index statements, idempotent via IF NOT EXISTS.
SCHEMA_STATEMENTS = [
    f"CREATE CONSTRAINT microservice_name IF NOT EXISTS FOR (n:{MICROSERVICE}) REQUIRE n.name IS UNIQUE",
    f"CREATE CONSTRAINT code_file_path IF NOT EXISTS FOR (n:{CODE_FILE}) REQUIRE n.path IS UNIQUE",
    f"CREATE CONSTRAINT pull_request_number IF NOT EXISTS FOR (n:{PULL_REQUEST}) REQUIRE n.number IS UNIQUE",
    f"CREATE CONSTRAINT jira_story_key IF NOT EXISTS FOR (n:{JIRA_STORY}) REQUIRE n.key IS UNIQUE",
    f"CREATE CONSTRAINT test_case_id IF NOT EXISTS FOR (n:{TEST_CASE}) REQUIRE n.id IS UNIQUE",
    f"CREATE CONSTRAINT api_route_key IF NOT EXISTS FOR (n:{API_ROUTE}) REQUIRE n.key IS UNIQUE",
    f"CREATE CONSTRAINT customer_flow_name IF NOT EXISTS FOR (n:{CUSTOMER_FLOW}) REQUIRE n.name IS UNIQUE",
    f"CREATE CONSTRAINT incident_id IF NOT EXISTS FOR (n:{INCIDENT}) REQUIRE n.id IS UNIQUE",
    f"CREATE CONSTRAINT release_version IF NOT EXISTS FOR (n:{RELEASE}) REQUIRE n.version IS UNIQUE",
]


def install_schema(cig) -> None:
    for statement in SCHEMA_STATEMENTS:
        cig.run(statement)
