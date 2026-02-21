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


PROXY_ENV_FILE = ".env"


def parse_proxy_url(url: str) -> dict[str, str]:
    """Parse a proxy URL into components.

    Accepts formats like:
        http://host:port
        http://user:pass@host:port

    Returns:
        Dict with host, port, username, password keys.

    Raises:
        ValueError: If the URL cannot be parsed or has no host.
    """
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host:
        raise ValueError(f"Invalid proxy URL (no host): {url}")

    return {
        "host": host,
        "port": str(parsed.port) if parsed.port else "",
        "username": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
    }


def load_proxy_url() -> str:
    """Load the saved proxy URL from ~/.config/firemd/.env.

    Returns:
        The proxy URL string, or empty string if not configured.
    """
    env_file = get_config_dir() / PROXY_ENV_FILE
    if not env_file.exists():
        return ""

    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        if key.strip() == "PROXY_URL":
            return val.strip()

    return ""


def save_proxy_url(url: str) -> Path:
    """Write proxy URL to ~/.config/firemd/.env.

    Returns:
        Path to the written file.
    """
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    env_file = config_dir / PROXY_ENV_FILE
    env_file.write_text(f"PROXY_URL={url}\n")
    return env_file


def clear_proxy_config() -> bool:
    """Remove the proxy configuration file.

    Returns:
        True if a file was removed, False if it didn't exist.
    """
    env_file = get_config_dir() / PROXY_ENV_FILE
    if env_file.exists():
        env_file.unlink()
        return True
    return False


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

