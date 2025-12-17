"""Manifest handling for tracking scrape progress and enabling resume."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ManifestEntry:
    """A single entry in the manifest file."""

    url: str
    file: str
    status: str  # "ok" or "error"
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    title: str | None = None
    http_status: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = {
            "url": self.url,
            "file": self.file,
            "status": self.status,
            "ts": self.ts,
        }
        if self.title:
            d["title"] = self.title
        if self.http_status:
            d["http_status"] = self.http_status
        if self.error:
            d["error"] = self.error
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManifestEntry":
        """Create from dictionary."""
        return cls(
            url=data["url"],
            file=data.get("file", ""),
            status=data["status"],
            ts=data.get("ts", ""),
            title=data.get("title"),
            http_status=data.get("http_status"),
            error=data.get("error"),
        )


def load_manifest(manifest_path: Path) -> dict[str, ManifestEntry]:
    """Load manifest from JSONL file.

    Args:
        manifest_path: Path to manifest.jsonl

    Returns:
        Dictionary mapping URL to ManifestEntry
    """
    entries: dict[str, ManifestEntry] = {}

    if not manifest_path.exists():
        return entries

    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entry = ManifestEntry.from_dict(data)
                entries[entry.url] = entry
            except (json.JSONDecodeError, KeyError):
                # Skip invalid lines
                continue

    return entries


def save_manifest_entry(manifest_path: Path, entry: ManifestEntry) -> None:
    """Append a single entry to the manifest file.

    Args:
        manifest_path: Path to manifest.jsonl
        entry: Entry to append
    """
    # Ensure parent directory exists
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with open(manifest_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry.to_dict()) + "\n")


def save_error_entry(errors_path: Path, entry: ManifestEntry) -> None:
    """Append an error entry to the errors file.

    Args:
        errors_path: Path to errors.jsonl
        entry: Error entry to append
    """
    if entry.status != "error":
        return

    # Ensure parent directory exists
    errors_path.parent.mkdir(parents=True, exist_ok=True)

    with open(errors_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry.to_dict()) + "\n")

