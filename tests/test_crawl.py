"""Tests for crawl functionality."""

import json
from unittest.mock import MagicMock, patch

import pytest

from firemd.firecrawl import CrawlJob, FirecrawlClient, FirecrawlError
from firemd.util import get_crawl_output_dir


class TestCrawlJob:
    """Tests for CrawlJob dataclass."""

    def test_defaults(self):
        """CrawlJob should have sensible defaults."""
        job = CrawlJob(job_id="abc123")
        assert job.job_id == "abc123"
        assert job.total == 0
        assert job.completed == 0
        assert job.status == "pending"

    def test_custom_values(self):
        """CrawlJob should accept custom values."""
        job = CrawlJob(job_id="xyz", total=100, completed=50, status="scraping")
        assert job.total == 100
        assert job.completed == 50
        assert job.status == "scraping"


class TestGetCrawlOutputDir:
    """Tests for get_crawl_output_dir function."""

    def test_extracts_domain(self, tmp_path, monkeypatch):
        """Should extract domain from URL as directory name."""
        monkeypatch.chdir(tmp_path)
        result = get_crawl_output_dir("https://docs.example.com/api/reference")
        assert result.name == "docs.example.com"

    def test_strips_port(self, tmp_path, monkeypatch):
        """Should strip port from domain."""
        monkeypatch.chdir(tmp_path)
        result = get_crawl_output_dir("http://localhost:3000/docs")
        assert result.name == "localhost"

    def test_explicit_out(self):
        """Should use explicit output when provided."""
        result = get_crawl_output_dir("https://example.com", explicit_out="/tmp/my-output")
        assert str(result) == "/tmp/my-output"

    def test_simple_domain(self, tmp_path, monkeypatch):
        """Should handle simple domains."""
        monkeypatch.chdir(tmp_path)
        result = get_crawl_output_dir("https://example.com")
        assert result.name == "example.com"

    def test_subdomain(self, tmp_path, monkeypatch):
        """Should preserve subdomains."""
        monkeypatch.chdir(tmp_path)
        result = get_crawl_output_dir("https://api.docs.example.com/v1")
        assert result.name == "api.docs.example.com"


class TestStartCrawl:
    """Tests for FirecrawlClient.start_crawl."""

    def test_basic_request(self):
        """Should send correct POST body."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "id": "crawl-123"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(FirecrawlClient, "_make_request", return_value=mock_response) as mock_req:
            client = FirecrawlClient()
            job = client.start_crawl("https://example.com")

            assert job.job_id == "crawl-123"
            assert job.status == "pending"

            call_args = mock_req.call_args
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/v1/crawl"
            body = call_args[1]["json"] if "json" in call_args[1] else call_args[0][2]
            assert body["url"] == "https://example.com"
            assert body["limit"] == 1000
            assert body["maxDepth"] == 10
            assert body["scrapeOptions"] == {"formats": ["markdown"]}

    def test_with_options(self):
        """Should include optional params when set."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "id": "crawl-456"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(FirecrawlClient, "_make_request", return_value=mock_response) as mock_req:
            client = FirecrawlClient()
            client.start_crawl(
                "https://example.com",
                limit=50,
                max_depth=3,
                include_paths=["/docs/*"],
                exclude_paths=["/blog/*"],
                allow_backward_links=True,
                allow_external_links=True,
                allow_subdomains=True,
                ignore_sitemap=True,
                ignore_robots_txt=True,
                wait_for=2000,
            )

            args = mock_req.call_args
            body = args[1].get("json") or args[0][2]
            assert body["limit"] == 50
            assert body["maxDepth"] == 3
            assert body["includePaths"] == ["/docs/*"]
            assert body["excludePaths"] == ["/blog/*"]
            assert body["allowBackwardLinks"] is True
            assert body["allowExternalLinks"] is True
            assert body["allowSubdomains"] is True
            assert body["ignoreSitemap"] is True
            assert body["ignoreRobotsTxt"] is True
            assert body["scrapeOptions"]["waitFor"] == 2000

    def test_excludes_false_booleans(self):
        """Should not include boolean params when False."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "id": "crawl-789"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(FirecrawlClient, "_make_request", return_value=mock_response) as mock_req:
            client = FirecrawlClient()
            client.start_crawl("https://example.com")

            args = mock_req.call_args
            body = args[1].get("json") or args[0][2]
            assert "allowBackwardLinks" not in body
            assert "allowExternalLinks" not in body
            assert "allowSubdomains" not in body
            assert "ignoreSitemap" not in body
            assert "ignoreRobotsTxt" not in body

    def test_error_response(self):
        """Should raise FirecrawlError on API error."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False, "error": "Invalid URL"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(FirecrawlClient, "_make_request", return_value=mock_response):
            client = FirecrawlClient()
            with pytest.raises(FirecrawlError, match="Invalid URL"):
                client.start_crawl("not-a-url")

    def test_fallback_id_from_url_field(self):
        """Should extract job ID from url field if id is missing."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "url": "http://localhost:3002/v1/crawl/abc-from-url",
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(FirecrawlClient, "_make_request", return_value=mock_response):
            client = FirecrawlClient()
            job = client.start_crawl("https://example.com")
            assert job.job_id == "abc-from-url"


class TestCancelCrawl:
    """Tests for FirecrawlClient.cancel_crawl."""

    def test_sends_delete(self):
        """Should send DELETE request."""
        with patch.object(FirecrawlClient, "_make_request") as mock_req:
            client = FirecrawlClient()
            client.cancel_crawl("crawl-123")
            mock_req.assert_called_once_with("DELETE", "/v1/crawl/crawl-123")

    def test_swallows_errors(self):
        """Should not raise on errors (best-effort)."""
        with patch.object(FirecrawlClient, "_make_request", side_effect=Exception("network")):
            client = FirecrawlClient()
            client.cancel_crawl("crawl-123")  # Should not raise


class TestWsUrl:
    """Tests for FirecrawlClient._ws_url."""

    def test_http_to_ws(self):
        """Should convert http to ws."""
        client = FirecrawlClient(api_url="http://localhost:3002")
        assert client._ws_url() == "ws://localhost:3002"

    def test_https_to_wss(self):
        """Should convert https to wss."""
        client = FirecrawlClient(api_url="https://api.example.com")
        assert client._ws_url() == "wss://api.example.com"

    def test_preserves_path(self):
        """Should preserve path in URL."""
        client = FirecrawlClient(api_url="http://localhost:3002/prefix")
        assert client._ws_url() == "ws://localhost:3002/prefix"


class TestStreamCrawlWs:
    """Tests for WebSocket-based crawl streaming."""

    def _make_ws_mock(self, messages):
        """Create a mock WebSocket that yields messages then raises."""
        ws = MagicMock()
        returns = [json.dumps(m) for m in messages]
        ws.recv = MagicMock(side_effect=returns)
        return ws

    def test_document_event(self):
        """Should yield ScrapeResult for document events."""
        messages = [
            {
                "type": "document",
                "data": {
                    "markdown": "# Hello",
                    "metadata": {
                        "sourceURL": "https://example.com/page1",
                        "title": "Page 1",
                        "statusCode": 200,
                    },
                },
            },
            {"type": "done"},
        ]
        ws = self._make_ws_mock(messages)

        with patch("websocket.create_connection", return_value=ws):
            client = FirecrawlClient()
            events = list(client._stream_crawl_ws("job-1"))

            # First event: document
            job, results = events[0]
            assert len(results) == 1
            assert results[0].url == "https://example.com/page1"
            assert results[0].markdown == "# Hello"
            assert results[0].title == "Page 1"
            assert job.completed == 1

            # Second event: done
            job, results = events[1]
            assert job.status == "completed"
            assert len(results) == 0

    def test_catchup_event(self):
        """Should yield documents from catchup data array."""
        messages = [
            {
                "type": "catchup",
                "data": {
                    "total": 50,
                    "completed": 3,
                    "status": "scraping",
                    "data": [
                        {
                            "markdown": "# Page A",
                            "metadata": {
                                "sourceURL": "https://example.com/a",
                                "statusCode": 200,
                            },
                        },
                        {
                            "markdown": "# Page B",
                            "metadata": {
                                "sourceURL": "https://example.com/b",
                                "statusCode": 200,
                            },
                        },
                    ],
                },
            },
            {"type": "done"},
        ]
        ws = self._make_ws_mock(messages)

        with patch("websocket.create_connection", return_value=ws):
            client = FirecrawlClient()
            snapshots = []
            for job, results in client._stream_crawl_ws("job-2"):
                snapshots.append((job.total, job.completed, job.status, list(results)))

            # First event: catchup with 2 documents
            total, completed, status, results = snapshots[0]
            assert total == 50
            assert completed == 3
            assert status == "scraping"
            assert len(results) == 2
            assert results[0].url == "https://example.com/a"
            assert results[1].url == "https://example.com/b"

            # Second event: done
            _, _, status, results = snapshots[1]
            assert status == "completed"
            assert len(results) == 0

    def test_error_event(self):
        """Should set failed status on error event."""
        messages = [
            {"type": "error", "data": {"message": "Something went wrong"}},
        ]
        ws = self._make_ws_mock(messages)

        with patch("websocket.create_connection", return_value=ws):
            client = FirecrawlClient()
            events = list(client._stream_crawl_ws("job-3"))

            job, results = events[0]
            assert job.status == "failed"
            assert len(results) == 0


class TestStreamCrawlFallback:
    """Tests for WebSocket fallback to HTTP polling."""

    def test_ws_failure_triggers_polling(self):
        """Should fall back to polling when WebSocket fails."""
        poll_response = MagicMock()
        poll_response.json.return_value = {
            "status": "completed",
            "total": 1,
            "completed": 1,
            "data": [
                {
                    "markdown": "# Polled",
                    "metadata": {
                        "sourceURL": "https://example.com",
                        "title": "Polled Page",
                        "statusCode": 200,
                    },
                }
            ],
        }
        poll_response.raise_for_status = MagicMock()

        with (
            patch.object(
                FirecrawlClient,
                "_stream_crawl_ws",
                side_effect=Exception("WS connection failed"),
            ),
            patch.object(FirecrawlClient, "_make_request", return_value=poll_response),
        ):
            client = FirecrawlClient()
            events = list(client.stream_crawl("job-4"))

            assert len(events) == 1
            job, results = events[0]
            assert job.status == "completed"
            assert len(results) == 1
            assert results[0].url == "https://example.com"
            assert results[0].markdown == "# Polled"


class TestPollCrawl:
    """Tests for HTTP polling crawl."""

    def test_deduplicates_urls(self):
        """Should not yield the same URL twice across polls."""
        responses = [
            MagicMock(
                json=MagicMock(return_value={
                    "status": "scraping",
                    "total": 2,
                    "completed": 1,
                    "data": [
                        {
                            "markdown": "# Page 1",
                            "metadata": {"sourceURL": "https://example.com/p1", "statusCode": 200},
                        }
                    ],
                }),
                raise_for_status=MagicMock(),
            ),
            MagicMock(
                json=MagicMock(return_value={
                    "status": "completed",
                    "total": 2,
                    "completed": 2,
                    "data": [
                        {
                            "markdown": "# Page 1",
                            "metadata": {"sourceURL": "https://example.com/p1", "statusCode": 200},
                        },
                        {
                            "markdown": "# Page 2",
                            "metadata": {"sourceURL": "https://example.com/p2", "statusCode": 200},
                        },
                    ],
                }),
                raise_for_status=MagicMock(),
            ),
        ]

        with patch.object(FirecrawlClient, "_make_request", side_effect=responses):
            with patch("time.sleep"):
                client = FirecrawlClient()
                all_results = []
                for job, results in client._poll_crawl("job-5", poll_interval=0.01):
                    all_results.extend(results)

                # p1 should appear only once, p2 once
                urls = [r.url for r in all_results]
                assert urls == ["https://example.com/p1", "https://example.com/p2"]
