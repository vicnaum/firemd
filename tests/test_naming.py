"""Tests for filename generation."""

import pytest

from firemd.outputs import make_filename, sanitize_for_filename, url_hash


class TestSanitizeForFilename:
    """Tests for sanitize_for_filename function."""

    def test_basic_text(self):
        """Basic alphanumeric text passes through."""
        assert sanitize_for_filename("hello") == "hello"
        assert sanitize_for_filename("Hello123") == "Hello123"

    def test_replaces_slashes(self):
        """Forward and back slashes become underscores."""
        assert sanitize_for_filename("path/to/file") == "path_to_file"
        assert sanitize_for_filename("path\\to\\file") == "path_to_file"

    def test_removes_special_chars(self):
        """Special characters are removed."""
        assert sanitize_for_filename("hello@world!") == "helloworld"
        assert sanitize_for_filename("a?b&c=d") == "abcd"

    def test_preserves_dots_underscores(self):
        """Dots and underscores are preserved, hyphens become underscores."""
        assert sanitize_for_filename("file.name") == "file.name"
        assert sanitize_for_filename("file_name") == "file_name"
        # Hyphens are collapsed to underscores for consistency
        assert sanitize_for_filename("file-name") == "file_name"

    def test_collapses_multiple_separators(self):
        """Multiple underscores/hyphens collapse to one."""
        assert sanitize_for_filename("a___b") == "a_b"
        assert sanitize_for_filename("a---b") == "a_b"

    def test_strips_leading_trailing(self):
        """Leading/trailing separators are stripped."""
        assert sanitize_for_filename("_hello_") == "hello"
        assert sanitize_for_filename("-hello-") == "hello"
        assert sanitize_for_filename(".hello.") == "hello"

    def test_max_length(self):
        """Truncates to max_length."""
        long_text = "a" * 100
        result = sanitize_for_filename(long_text, max_length=50)
        assert len(result) == 50

    def test_empty_input(self):
        """Empty input returns empty string."""
        assert sanitize_for_filename("") == ""


class TestUrlHash:
    """Tests for url_hash function."""

    def test_returns_correct_length(self):
        """Returns hash of specified length."""
        result = url_hash("https://example.com", length=10)
        assert len(result) == 10

    def test_different_urls_different_hashes(self):
        """Different URLs produce different hashes."""
        hash1 = url_hash("https://example.com/page1")
        hash2 = url_hash("https://example.com/page2")
        assert hash1 != hash2

    def test_same_url_same_hash(self):
        """Same URL always produces same hash."""
        url = "https://example.com/page"
        assert url_hash(url) == url_hash(url)

    def test_hex_characters(self):
        """Hash contains only hex characters."""
        result = url_hash("https://example.com")
        assert all(c in "0123456789abcdef" for c in result)


class TestMakeFilename:
    """Tests for make_filename function."""

    def test_simple_url(self):
        """Simple URL generates expected filename."""
        filename = make_filename("https://example.com")
        assert filename.startswith("example.com")
        assert filename.endswith(".md")
        assert "__" in filename  # Has hash separator

    def test_url_with_path(self):
        """URL with path includes path slug."""
        filename = make_filename("https://example.com/docs/intro")
        assert "example.com" in filename
        assert "docs_intro" in filename
        assert filename.endswith(".md")

    def test_with_index(self):
        """Index is zero-padded and prepended."""
        filename = make_filename("https://example.com", index=1)
        assert filename.startswith("0001_")

        filename = make_filename("https://example.com", index=42)
        assert filename.startswith("0042_")

    def test_collision_resistance(self):
        """Similar URLs get different filenames due to hash."""
        f1 = make_filename("https://example.com/page?a=1")
        f2 = make_filename("https://example.com/page?a=2")
        assert f1 != f2

    def test_url_without_path(self):
        """URL without path uses 'index' as path slug."""
        filename = make_filename("https://example.com/")
        assert "index" in filename or "example.com__" in filename

    def test_special_characters_in_path(self):
        """Special characters in path are sanitized."""
        filename = make_filename("https://example.com/hello%20world?foo=bar")
        # Should not contain special chars
        assert "%" not in filename
        assert "?" not in filename
        assert "=" not in filename

    def test_long_path_truncated(self):
        """Very long paths are truncated."""
        long_path = "/".join(["segment"] * 50)
        filename = make_filename(f"https://example.com{long_path}")
        # Filename should be reasonable length
        assert len(filename) < 150

