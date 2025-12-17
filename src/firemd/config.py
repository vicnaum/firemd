"""Configuration and paths for firemd."""

from pathlib import Path

import platformdirs

# Application name for platformdirs
APP_NAME = "firemd"

# Default Firecrawl API settings
DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 3002
DEFAULT_API_URL = f"http://{DEFAULT_API_HOST}:{DEFAULT_API_PORT}"

# Health check endpoint
HEALTH_ENDPOINT = "/v0/health/liveness"

# Firecrawl git repository
FIRECRAWL_REPO_URL = "https://github.com/mendableai/firecrawl.git"


def get_state_dir() -> Path:
    """Get the state directory for firemd (~/.local/share/firemd/)."""
    return Path(platformdirs.user_data_dir(APP_NAME))


def get_firecrawl_dir() -> Path:
    """Get the directory where Firecrawl is cloned."""
    return get_state_dir() / "firecrawl"


def get_cache_dir() -> Path:
    """Get the cache directory for firemd (~/.cache/firemd/)."""
    return Path(platformdirs.user_cache_dir(APP_NAME))


def get_config_dir() -> Path:
    """Get the config directory for firemd (~/.config/firemd/)."""
    return Path(platformdirs.user_config_dir(APP_NAME))


# Default .env content for Firecrawl
def get_default_env_content(bull_auth_key: str) -> str:
    """Generate default .env content for Firecrawl."""
    return f"""\
# Firecrawl configuration (managed by firemd)
# IMPORTANT:
# Firecrawl's docker-compose.yaml publishes ports like:
#   - "${{PORT:-3002}}:${{INTERNAL_PORT:-3002}}"
# To bind to localhost only without a compose override (which would append),
# we set PORT to include the host IP.
PORT={DEFAULT_API_HOST}:{DEFAULT_API_PORT}
INTERNAL_PORT={DEFAULT_API_PORT}
HOST=0.0.0.0
USE_DB_AUTHENTICATION=false
BULL_AUTH_KEY={bull_auth_key}
NUM_WORKERS_PER_QUEUE=2

# Optional vars referenced by Firecrawl compose; set to empty to avoid noisy warnings
PROXY_SERVER=
PROXY_USERNAME=
PROXY_PASSWORD=
BLOCK_MEDIA=
OPENAI_API_KEY=
OPENAI_BASE_URL=
MODEL_NAME=
MODEL_EMBEDDING_NAME=
OLLAMA_BASE_URL=
TEST_API_KEY=
SUPABASE_ANON_TOKEN=
SUPABASE_URL=
SUPABASE_SERVICE_TOKEN=
SELF_HOSTED_WEBHOOK_URL=
LOGGING_LEVEL=
SEARXNG_ENDPOINT=
SEARXNG_ENGINES=
SEARXNG_CATEGORIES=
SLACK_WEBHOOK_URL=
"""

