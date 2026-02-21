"""Utility functions for firemd."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse


def is_url(text: str) -> bool:
    """Check if text looks like a URL.

    Args:
        text: Text to check

    Returns:
        True if text appears to be a URL
    """
    # Simple check for http:// or https://
    return bool(re.match(r"^https?://", text.strip(), re.IGNORECASE))


def parse_url_file(filepath: Path) -> list[str]:
    """Parse a file containing URLs (one per line).

    Ignores blank lines and lines starting with #.

    Args:
        filepath: Path to the URL file

    Returns:
        List of URLs
    """
    urls = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    return urls


def get_output_dir(input_path: str | Path, explicit_out: str | None = None) -> Path:
    """Determine the output directory based on input.

    Args:
        input_path: The input (URL or file path)
        explicit_out: Explicitly specified output directory

    Returns:
        Path to output directory
    """
    if explicit_out:
        return Path(explicit_out)

    # If input is a URL, output to current directory
    if isinstance(input_path, str) and is_url(input_path):
        return Path.cwd()

    # If input is a file, output to directory named after file (without extension)
    input_path = Path(input_path)
    return Path.cwd() / input_path.stem


def get_crawl_output_dir(url: str, explicit_out: str | None = None) -> Path:
    """Determine output directory for a crawl based on the starting URL.

    Uses the domain (hostname without port) as the directory name.

    Args:
        url: The starting crawl URL
        explicit_out: Explicitly specified output directory

    Returns:
        Path to output directory
    """
    if explicit_out:
        return Path(explicit_out)

    parsed = urlparse(url)
    domain = parsed.hostname or "unknown"
    return Path.cwd() / domain

