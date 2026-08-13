import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env", override=True)


def env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


def get(key: str, default: str | None = None) -> str | None:
    """Look up a setting even if this module was imported before the attr existed."""
    val = globals().get(key)
    if val is None or val == "":
        val = os.getenv(key, default)
    return val


def setting(key: str, default: str | None = None) -> str:
    """Stripped config value; empty string when unset."""
    return (get(key, default) or "").strip()


NEO4J_URI = env("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = env("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = env("NEO4J_PASSWORD", "changeme")

OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", "LFM2.5:Q4")

GITHUB_TOKEN = env("GITHUB_TOKEN")
GITHUB_REPO_OWNER = env("GITHUB_REPO_OWNER")
GITHUB_REPO_NAME = env("GITHUB_REPO_NAME")
# Optional CIG PR → GitHub PR map, e.g. "482:1,500:2"
GITHUB_PR_MAP = env("GITHUB_PR_MAP", "")
# auto | mcp | fixture  (auto uses GitHub MCP when token set)
GITHUB_SOURCE = (env("GITHUB_SOURCE", "auto") or "auto").strip().lower()

# mcp | cloud (alias of mcp) | local
JIRA_SOURCE = (env("JIRA_SOURCE", "local") or "local").strip().lower()
JIRA_BASE_URL = env("JIRA_BASE_URL")
JIRA_EMAIL = env("JIRA_EMAIL")
JIRA_API_TOKEN = env("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = env("JIRA_PROJECT_KEY", "AEG")
JIRA_PROJECT_NAME = env("JIRA_PROJECT_NAME", "Project AEGIS")

# MCP stdio servers (GitHub + Jira — no in-app REST)
MCP_GITHUB_COMMAND = env("MCP_GITHUB_COMMAND", "npx")
MCP_GITHUB_PACKAGE = env("MCP_GITHUB_PACKAGE", "@modelcontextprotocol/server-github")
MCP_GITHUB_ARGS = env("MCP_GITHUB_ARGS")
MCP_JIRA_COMMAND = env("MCP_JIRA_COMMAND", "npx")
MCP_JIRA_PACKAGE = env("MCP_JIRA_PACKAGE", "@aashari/mcp-server-atlassian-jira")
MCP_JIRA_ARGS = env("MCP_JIRA_ARGS")

# Keys the Infrastructure page can edit and persist to .env
MCP_CONFIG_KEYS = (
    "GITHUB_SOURCE",
    "GITHUB_TOKEN",
    "GITHUB_REPO_OWNER",
    "GITHUB_REPO_NAME",
    "GITHUB_PR_MAP",
    "MCP_GITHUB_COMMAND",
    "MCP_GITHUB_PACKAGE",
    "MCP_GITHUB_ARGS",
    "JIRA_SOURCE",
    "JIRA_BASE_URL",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "JIRA_PROJECT_KEY",
    "JIRA_PROJECT_NAME",
    "MCP_JIRA_COMMAND",
    "MCP_JIRA_PACKAGE",
    "MCP_JIRA_ARGS",
)

SECRET_KEYS = frozenset({"GITHUB_TOKEN", "JIRA_API_TOKEN", "NEO4J_PASSWORD"})


def upsert_env_file(updates: dict[str, str], path: Path | None = None) -> None:
    """Replace or append KEY=value lines in .env, preserving comments."""
    env_path = path or (BASE_DIR / ".env")
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.is_file() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    missing = [k for k in updates if k not in seen]
    if missing:
        if out and out[-1].strip():
            out.append("")
        for key in missing:
            out.append(f"{key}={updates[key]}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def apply_updates(updates: dict[str, str], *, env_path: Path | None = None) -> list[str]:
    """Persist MCP/integration settings to .env and the live process."""
    cleaned: dict[str, str] = {}
    for key, value in updates.items():
        if key not in MCP_CONFIG_KEYS:
            continue
        if value is None:
            continue
        text = str(value).strip()
        if key in SECRET_KEYS and not text:
            continue
        cleaned[key] = text
    if not cleaned:
        return []
    upsert_env_file(cleaned, env_path)
    for key, value in cleaned.items():
        os.environ[key] = value
        globals()[key] = value
    return list(cleaned.keys())
