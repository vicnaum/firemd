"""Output handling for firemd - filename generation, markdown writing."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from firemd.firecrawl import ScrapeResult


def sanitize_for_filename(text: str, max_length: int = 50) -> str:
    """Sanitize text for use in a filename.

    Keeps only alphanumeric, dots, underscores, and hyphens.

    Args:
        text: Text to sanitize
        max_length: Maximum length of result

    Returns:
        Sanitized string safe for filenames
    """
    # Replace common separators with underscores
    text = re.sub(r"[/\\]", "_", text)
    # Remove anything that's not alphanumeric, dot, underscore, or hyphen
    text = re.sub(r"[^A-Za-z0-9._-]", "", text)
    # Collapse multiple underscores/hyphens
    text = re.sub(r"[_-]+", "_", text)
    # Strip leading/trailing underscores
    text = text.strip("_-.")
    # Truncate
    return text[:max_length]


def url_hash(url: str, length: int = 10) -> str:
    """Generate a short hash of a URL.

    Args:
        url: URL to hash
        length: Length of hash to return

    Returns:
        First `length` characters of SHA1 hex digest
    """
    return hashlib.sha1(url.encode()).hexdigest()[:length]


def make_filename(url: str, index: int | None = None) -> str:
    """Generate a stable, collision-resistant filename for a URL.

    Filename scheme: {index_}{host}_{path_slug}__{hash}.md

    Args:
        url: The source URL
        index: Optional index for batch operations (1-based, zero-padded)

    Returns:
        Filename string (without directory)
    """
    parsed = urlparse(url)

    # Extract and sanitize host
    host = parsed.netloc or "unknown"
    host = sanitize_for_filename(host, max_length=30)

    # Extract and sanitize path
    path = parsed.path.strip("/")
    if path:
        path_slug = sanitize_for_filename(path, max_length=40)
    else:
        path_slug = "index"

    # Generate hash
    hash_suffix = url_hash(url)

    # Build filename
    parts = []
    if index is not None:
        parts.append(f"{index:04d}")
    parts.append(host)
    if path_slug and path_slug != host:
        parts.append(path_slug)

    base = "_".join(parts)
    return f"{base}__{hash_suffix}.md"


def generate_front_matter(result: ScrapeResult) -> str:
    """Generate YAML front matter for a scrape result.

    Args:
        result: The scrape result

    Returns:
        YAML front matter string including delimiters
    """
    lines = ["---"]
    lines.append(f"url: {result.url}")
    if result.title:
        # Escape quotes in title
        title = result.title.replace('"', '\\"')
        lines.append(f'title: "{title}"')
    if result.source_url and result.source_url != result.url:
        lines.append(f"source_url: {result.source_url}")
    lines.append(f"scraped_at: {result.scraped_at.isoformat()}")
    if result.status_code:
        lines.append(f"status_code: {result.status_code}")
    lines.append("---")
    lines.append("")  # Blank line after front matter
    return "\n".join(lines)


def write_markdown(
    output_dir: Path,
    result: ScrapeResult,
    index: int | None = None,
    front_matter: bool = False,
) -> Path:
    """Write a scrape result to a markdown file.

    Args:
        output_dir: Directory to write to
        result: The scrape result
        index: Optional index for batch operations
        front_matter: Whether to include YAML front matter

    Returns:
        Path to the written file
    """
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename
    filename = make_filename(result.url, index=index)
    filepath = output_dir / filename

    # Build content
    content_parts = []
    if front_matter:
        content_parts.append(generate_front_matter(result))
    content_parts.append(result.markdown)

    content = "\n".join(content_parts) if front_matter else result.markdown

    # Write file
    filepath.write_text(content, encoding="utf-8")

    return filepath

