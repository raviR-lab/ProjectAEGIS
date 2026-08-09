"""Project AEGIS - AI-driven release shield."""

import os

__version__ = "0.1.0"

# CrewAI registers SIGTERM/SIGINT handlers at import, which is illegal inside
# Streamlit's background thread. Disable its telemetry so imports are safe.
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
