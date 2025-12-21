"""Tests for retry logic and error classification."""

import pytest

from firemd.firecrawl import is_permanent_error, is_success, ScrapeResult


class TestIsPermanentError:
    """Tests for is_permanent_error function."""

    def test_none_status_code_is_retryable(self):
        """Network errors (None status) should be retried."""
        assert is_permanent_error(None) is False

    def test_2xx_is_not_permanent(self):
        """Success codes are not permanent errors."""
        for code in [200, 201, 204]:
            assert is_permanent_error(code) is False

    def test_408_is_retryable(self):
        """408 Request Timeout should be retried."""
        assert is_permanent_error(408) is False

    def test_429_is_retryable(self):
        """429 Too Many Requests should be retried."""
        assert is_permanent_error(429) is False

    def test_4xx_except_408_429_are_permanent(self):
        """Other 4xx errors are permanent."""
        permanent_codes = [400, 401, 403, 404, 405, 410, 418, 422, 451]
        for code in permanent_codes:
            assert is_permanent_error(code) is True, f"{code} should be permanent"

    def test_5xx_are_retryable(self):
        """5xx server errors should be retried."""
        for code in [500, 502, 503, 504, 505, 507]:
            assert is_permanent_error(code) is False, f"{code} should be retryable"

    def test_unusual_codes_are_retryable(self):
        """Unknown/unusual codes should be retried."""
        # 1xx informational, 3xx redirects, etc.
        for code in [100, 301, 302, 999]:
            assert is_permanent_error(code) is False


class TestIsSuccess:
    """Tests for is_success function."""

    def test_none_is_not_success(self):
        """None status code is not success."""
        assert is_success(None) is False

    def test_2xx_is_success(self):
        """2xx codes are success."""
        for code in [200, 201, 202, 204, 206]:
            assert is_success(code) is True, f"{code} should be success"

    def test_1xx_is_not_success(self):
        """1xx codes are not success."""
        for code in [100, 101]:
            assert is_success(code) is False

    def test_3xx_is_not_success(self):
        """3xx codes are not success."""
        for code in [301, 302, 304]:
            assert is_success(code) is False

    def test_4xx_is_not_success(self):
        """4xx codes are not success."""
        for code in [400, 401, 403, 404, 429]:
            assert is_success(code) is False

    def test_5xx_is_not_success(self):
        """5xx codes are not success."""
        for code in [500, 502, 503]:
            assert is_success(code) is False


class TestScrapeResultSuccess:
    """Tests for ScrapeResult.success property."""

    def test_success_requires_2xx_and_content(self):
        """Success requires both 2xx status and markdown content."""
        result = ScrapeResult(
            url="https://example.com",
            markdown="# Hello",
            status_code=200,
        )
        assert result.success is True

    def test_429_with_content_is_not_success(self):
        """429 with content is not success (rate limit page)."""
        result = ScrapeResult(
            url="https://example.com",
            markdown="Slow down, too many requests",
            status_code=429,
        )
        assert result.success is False

    def test_200_without_content_is_not_success(self):
        """200 without markdown content is not success."""
        result = ScrapeResult(
            url="https://example.com",
            markdown="",
            status_code=200,
        )
        assert result.success is False

    def test_none_status_code_is_not_success(self):
        """Missing status code (network error) is not success."""
        result = ScrapeResult(
            url="https://example.com",
            markdown="# Hello",
            status_code=None,
        )
        assert result.success is False

    def test_404_with_content_is_not_success(self):
        """404 with content is not success."""
        result = ScrapeResult(
            url="https://example.com",
            markdown="Page not found",
            status_code=404,
        )
        assert result.success is False


class TestErrorClassificationIntegration:
    """Integration tests for error classification with ScrapeResult."""

    def test_rate_limit_scenario(self):
        """Rate limit response should be retryable, not successful."""
        result = ScrapeResult(
            url="https://example.com",
            markdown="Slow down, too many requests",
            status_code=429,
        )
        assert result.success is False
        assert is_permanent_error(result.status_code) is False  # Should retry

    def test_not_found_scenario(self):
        """404 response should be permanent error."""
        result = ScrapeResult(
            url="https://example.com/deleted",
            markdown="Page not found",
            status_code=404,
        )
        assert result.success is False
        assert is_permanent_error(result.status_code) is True  # Don't retry

    def test_server_error_scenario(self):
        """500 response should be retryable."""
        result = ScrapeResult(
            url="https://example.com",
            markdown="",
            status_code=500,
            error="Internal Server Error",
        )
        assert result.success is False
        assert is_permanent_error(result.status_code) is False  # Should retry

    def test_network_error_scenario(self):
        """Network error (no status code) should be retryable."""
        result = ScrapeResult(
            url="https://example.com",
            markdown="",
            status_code=None,
            error="Connection refused",
        )
        assert result.success is False
        assert is_permanent_error(result.status_code) is False  # Should retry

