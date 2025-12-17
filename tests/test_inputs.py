"""Tests for input parsing and URL detection."""

import tempfile
from pathlib import Path

import pytest

from firemd.util import get_output_dir, is_url, parse_url_file


class TestIsUrl:
    """Tests for is_url function."""

    def test_http_url(self):
        """HTTP URLs are detected."""
        assert is_url("http://example.com")
        assert is_url("http://example.com/path")

    def test_https_url(self):
        """HTTPS URLs are detected."""
        assert is_url("https://example.com")
        assert is_url("https://example.com/path?query=1")

    def test_case_insensitive(self):
        """URL detection is case-insensitive."""
        assert is_url("HTTP://example.com")
        assert is_url("HTTPS://example.com")
        assert is_url("hTtPs://example.com")

    def test_with_whitespace(self):
        """Whitespace is trimmed before checking."""
        assert is_url("  https://example.com  ")
        assert is_url("\thttps://example.com\n")

    def test_file_path_not_url(self):
        """File paths are not URLs."""
        assert not is_url("/path/to/file.txt")
        assert not is_url("./relative/path.txt")
        assert not is_url("file.txt")

    def test_other_schemes_not_url(self):
        """Other schemes are not detected (only http/https)."""
        assert not is_url("ftp://example.com")
        assert not is_url("file://path/to/file")
        assert not is_url("mailto:user@example.com")


class TestParseUrlFile:
    """Tests for parse_url_file function."""

    def test_simple_file(self):
        """Parses simple file with one URL per line."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("https://example.com\n")
            f.write("https://example.org\n")
            f.write("https://example.net\n")
            f.flush()

            urls = parse_url_file(Path(f.name))
            assert urls == [
                "https://example.com",
                "https://example.org",
                "https://example.net",
            ]

    def test_ignores_blank_lines(self):
        """Blank lines are ignored."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("https://example.com\n")
            f.write("\n")
            f.write("   \n")
            f.write("https://example.org\n")
            f.flush()

            urls = parse_url_file(Path(f.name))
            assert urls == ["https://example.com", "https://example.org"]

    def test_ignores_comments(self):
        """Lines starting with # are ignored."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# This is a comment\n")
            f.write("https://example.com\n")
            f.write("  # Another comment\n")
            f.write("https://example.org\n")
            f.flush()

            urls = parse_url_file(Path(f.name))
            # Note: "  # Another comment" doesn't start with # after strip
            assert "https://example.com" in urls
            assert "https://example.org" in urls

    def test_strips_whitespace(self):
        """Whitespace is stripped from URLs."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("  https://example.com  \n")
            f.write("\thttps://example.org\t\n")
            f.flush()

            urls = parse_url_file(Path(f.name))
            assert urls == ["https://example.com", "https://example.org"]

    def test_empty_file(self):
        """Empty file returns empty list."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("")
            f.flush()

            urls = parse_url_file(Path(f.name))
            assert urls == []


class TestGetOutputDir:
    """Tests for get_output_dir function."""

    def test_explicit_out_takes_precedence(self):
        """Explicit --out always wins."""
        result = get_output_dir("https://example.com", explicit_out="/custom/path")
        assert result == Path("/custom/path")

        result = get_output_dir("/some/file.txt", explicit_out="/custom/path")
        assert result == Path("/custom/path")

    def test_url_defaults_to_cwd(self):
        """URL input defaults to current directory."""
        result = get_output_dir("https://example.com", explicit_out=None)
        assert result == Path.cwd()

    def test_file_defaults_to_stem_dir(self):
        """File input defaults to directory named after file stem."""
        result = get_output_dir("/path/to/urls.txt", explicit_out=None)
        assert result == Path.cwd() / "urls"

        result = get_output_dir("myfile.txt", explicit_out=None)
        assert result == Path.cwd() / "myfile"

