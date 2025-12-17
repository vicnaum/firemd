"""Tests for manifest handling."""

import json
import tempfile
from pathlib import Path

import pytest

from firemd.manifest import ManifestEntry, load_manifest, save_manifest_entry


class TestManifestEntry:
    """Tests for ManifestEntry dataclass."""

    def test_to_dict_minimal(self):
        """Minimal entry converts to dict correctly."""
        entry = ManifestEntry(
            url="https://example.com",
            file="example.com__abc123.md",
            status="ok",
        )
        d = entry.to_dict()
        assert d["url"] == "https://example.com"
        assert d["file"] == "example.com__abc123.md"
        assert d["status"] == "ok"
        assert "ts" in d

    def test_to_dict_with_optional_fields(self):
        """Entry with optional fields includes them."""
        entry = ManifestEntry(
            url="https://example.com",
            file="example.com__abc123.md",
            status="ok",
            title="Example Title",
            http_status=200,
        )
        d = entry.to_dict()
        assert d["title"] == "Example Title"
        assert d["http_status"] == 200

    def test_to_dict_error_entry(self):
        """Error entry includes error message."""
        entry = ManifestEntry(
            url="https://example.com",
            file="",
            status="error",
            error="Connection timeout",
        )
        d = entry.to_dict()
        assert d["status"] == "error"
        assert d["error"] == "Connection timeout"

    def test_from_dict(self):
        """Creates entry from dict."""
        d = {
            "url": "https://example.com",
            "file": "example.md",
            "status": "ok",
            "ts": "2024-01-01T00:00:00",
            "title": "Title",
        }
        entry = ManifestEntry.from_dict(d)
        assert entry.url == "https://example.com"
        assert entry.file == "example.md"
        assert entry.status == "ok"
        assert entry.title == "Title"


class TestLoadManifest:
    """Tests for load_manifest function."""

    def test_load_empty_file(self):
        """Empty file returns empty dict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("")
            f.flush()
            result = load_manifest(Path(f.name))
            assert result == {}

    def test_load_nonexistent_file(self):
        """Nonexistent file returns empty dict."""
        result = load_manifest(Path("/nonexistent/manifest.jsonl"))
        assert result == {}

    def test_load_single_entry(self):
        """Loads single entry correctly."""
        entry = {"url": "https://example.com", "file": "example.md", "status": "ok"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()

            result = load_manifest(Path(f.name))
            assert "https://example.com" in result
            assert result["https://example.com"].status == "ok"

    def test_load_multiple_entries(self):
        """Loads multiple entries correctly."""
        entries = [
            {"url": "https://example.com", "file": "a.md", "status": "ok"},
            {"url": "https://example.org", "file": "b.md", "status": "ok"},
            {"url": "https://example.net", "file": "c.md", "status": "error", "error": "failed"},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
            f.flush()

            result = load_manifest(Path(f.name))
            assert len(result) == 3
            assert result["https://example.net"].status == "error"

    def test_ignores_invalid_json(self):
        """Invalid JSON lines are skipped."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"url": "https://example.com", "file": "a.md", "status": "ok"}\n')
            f.write("not valid json\n")
            f.write('{"url": "https://example.org", "file": "b.md", "status": "ok"}\n')
            f.flush()

            result = load_manifest(Path(f.name))
            assert len(result) == 2

    def test_last_entry_wins(self):
        """If same URL appears twice, last entry wins."""
        entries = [
            {"url": "https://example.com", "file": "a.md", "status": "error"},
            {"url": "https://example.com", "file": "b.md", "status": "ok"},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
            f.flush()

            result = load_manifest(Path(f.name))
            assert result["https://example.com"].status == "ok"
            assert result["https://example.com"].file == "b.md"


class TestSaveManifestEntry:
    """Tests for save_manifest_entry function."""

    def test_appends_to_file(self):
        """Entries are appended to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.jsonl"

            entry1 = ManifestEntry(url="https://example.com", file="a.md", status="ok")
            entry2 = ManifestEntry(url="https://example.org", file="b.md", status="ok")

            save_manifest_entry(manifest_path, entry1)
            save_manifest_entry(manifest_path, entry2)

            # Read back and verify
            with open(manifest_path) as f:
                lines = f.readlines()
            assert len(lines) == 2

    def test_creates_parent_directories(self):
        """Creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "subdir" / "nested" / "manifest.jsonl"

            entry = ManifestEntry(url="https://example.com", file="a.md", status="ok")
            save_manifest_entry(manifest_path, entry)

            assert manifest_path.exists()

    def test_written_entry_is_valid_json(self):
        """Written entries are valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.jsonl"

            entry = ManifestEntry(
                url="https://example.com",
                file="a.md",
                status="ok",
                title="Test Title",
            )
            save_manifest_entry(manifest_path, entry)

            with open(manifest_path) as f:
                data = json.loads(f.read().strip())
            assert data["url"] == "https://example.com"
            assert data["title"] == "Test Title"

