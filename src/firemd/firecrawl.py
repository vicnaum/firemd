"""Firecrawl API client."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, TypeVar

import httpx

from firemd.config import DEFAULT_API_URL

T = TypeVar("T")


# HTTP status codes that should trigger a retry (used by with_retry for API calls)
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def is_permanent_error(status_code: int | None) -> bool:
    """Check if an HTTP status code represents a permanent error that should NOT be retried.

    Permanent errors are 4xx client errors (except 408 Request Timeout and 429 Too Many Requests).
    These indicate issues that won't resolve with retrying (e.g., 404 Not Found, 403 Forbidden).

    Args:
        status_code: HTTP status code, or None for network errors

    Returns:
        True if the error is permanent and should not be retried
    """
    if status_code is None:
        return False  # Network error - should retry
    # 4xx are permanent EXCEPT 408 (timeout) and 429 (rate limit)
    if 400 <= status_code < 500 and status_code not in {408, 429}:
        return True
    return False  # 5xx, 408, 429, unknown = retry


def is_success(status_code: int | None) -> bool:
    """Check if an HTTP status code indicates success (2xx).

    Args:
        status_code: HTTP status code, or None

    Returns:
        True if status code is in the 2xx range
    """
    if status_code is None:
        return False
    return 200 <= status_code < 300


def with_retry(
    func: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple = (httpx.RequestError,),
) -> T:
    """Execute a function with exponential backoff retry.

    Args:
        func: Function to execute
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries
        retryable_exceptions: Tuple of exception types that should trigger retry

    Returns:
        Result of the function

    Raises:
        The last exception if all retries fail
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in RETRYABLE_STATUS_CODES:
                raise
            last_exception = e
        except retryable_exceptions as e:
            last_exception = e

        if attempt < max_retries:
            # Exponential backoff with jitter
            delay = min(base_delay * (2**attempt), max_delay)
            time.sleep(delay)

    # All retries exhausted
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic error")


@dataclass
class ScrapeResult:
    """Result of scraping a URL."""

    url: str
    markdown: str
    title: str | None = None
    description: str | None = None
    source_url: str | None = None
    status_code: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def success(self) -> bool:
        """Check if scrape was successful (2xx status and has content)."""
        return is_success(self.status_code) and bool(self.markdown)


@dataclass
class BatchJob:
    """Represents a batch scrape job."""

    job_id: str
    total: int
    completed: int = 0
    status: str = "pending"


class FirecrawlError(Exception):
    """Error from Firecrawl API."""

    pass


class FirecrawlClient:
    """Client for the Firecrawl API."""

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "FirecrawlClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            json: JSON body for POST requests

        Returns:
            HTTP response
        """

        def do_request() -> httpx.Response:
            if method.upper() == "GET":
                response = self.client.get(f"{self.api_url}{endpoint}")
            elif method.upper() == "POST":
                response = self.client.post(f"{self.api_url}{endpoint}", json=json)
            else:
                raise ValueError(f"Unsupported method: {method}")
            response.raise_for_status()
            return response

        return with_retry(do_request, max_retries=self.max_retries)

    def scrape_url(self, url: str) -> ScrapeResult:
        """Scrape a single URL and return markdown.

        Args:
            url: The URL to scrape

        Returns:
            ScrapeResult with markdown content
        """
        try:
            response = self._make_request(
                "POST",
                "/v1/scrape",
                json={
                    "url": url,
                    "formats": ["markdown"],
                },
            )
            data = response.json()

            # Handle API response format
            if not data.get("success", False):
                return ScrapeResult(
                    url=url,
                    markdown="",
                    error=data.get("error", "Unknown error"),
                )

            # Extract data from response
            result_data = data.get("data", {})
            metadata = result_data.get("metadata", {})

            return ScrapeResult(
                url=url,
                markdown=result_data.get("markdown", ""),
                title=metadata.get("title"),
                description=metadata.get("description"),
                source_url=metadata.get("sourceURL", url),
                status_code=metadata.get("statusCode"),
                metadata=metadata,
            )

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}"
            try:
                error_data = e.response.json()
                if "error" in error_data:
                    error_msg = error_data["error"]
            except Exception:
                pass
            return ScrapeResult(url=url, markdown="", error=error_msg)

        except httpx.RequestError as e:
            return ScrapeResult(url=url, markdown="", error=f"Request failed: {e}")

    def batch_scrape(self, urls: list[str]) -> BatchJob:
        """Start a batch scrape job.

        Args:
            urls: List of URLs to scrape

        Returns:
            BatchJob with job ID for polling
        """
        try:
            response = self._make_request(
                "POST",
                "/v1/batch/scrape",
                json={
                    "urls": urls,
                    "formats": ["markdown"],
                },
            )
            data = response.json()

            if not data.get("success", False):
                raise FirecrawlError(data.get("error", "Failed to start batch job"))

            # Extract job ID from response
            job_id = data.get("id", "")
            if not job_id:
                # Try to extract from url field
                url_field = data.get("url", "")
                if url_field:
                    job_id = url_field.split("/")[-1]

            return BatchJob(
                job_id=job_id,
                total=len(urls),
                status="pending",
            )

        except httpx.HTTPStatusError as e:
            raise FirecrawlError(f"HTTP {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise FirecrawlError(f"Request failed: {e}")

    def get_batch_status(self, job_id: str) -> dict[str, Any]:
        """Get the status of a batch scrape job.

        Args:
            job_id: The job ID to check

        Returns:
            Status dict with completed count, status, and results
        """
        try:
            response = self._make_request("GET", f"/v1/batch/scrape/{job_id}")
            return response.json()
        except httpx.HTTPStatusError as e:
            raise FirecrawlError(f"HTTP {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise FirecrawlError(f"Request failed: {e}")

    def poll_batch(
        self,
        job_id: str,
        poll_interval: float = 2.0,
    ) -> Iterator[tuple[BatchJob, list[ScrapeResult]]]:
        """Poll a batch job until completion, yielding results as they arrive.

        Args:
            job_id: The job ID to poll
            poll_interval: Seconds between polls

        Yields:
            Tuple of (BatchJob status, list of new ScrapeResult)
        """
        seen_urls: set[str] = set()

        while True:
            status_data = self.get_batch_status(job_id)

            status = status_data.get("status", "unknown")
            total = status_data.get("total", 0)
            completed = status_data.get("completed", 0)
            data_list = status_data.get("data", [])

            # Create job status
            job = BatchJob(
                job_id=job_id,
                total=total,
                completed=completed,
                status=status,
            )

            # Extract new results
            new_results: list[ScrapeResult] = []
            for item in data_list:
                url = item.get("metadata", {}).get("sourceURL", "")
                if not url:
                    url = item.get("url", "")

                if url and url not in seen_urls:
                    seen_urls.add(url)
                    metadata = item.get("metadata", {})
                    new_results.append(
                        ScrapeResult(
                            url=url,
                            markdown=item.get("markdown", ""),
                            title=metadata.get("title"),
                            description=metadata.get("description"),
                            source_url=metadata.get("sourceURL"),
                            status_code=metadata.get("statusCode"),
                            metadata=metadata,
                        )
                    )

            yield job, new_results

            # Check if done
            if status in ("completed", "failed", "cancelled"):
                break

            time.sleep(poll_interval)

    def scrape_urls_sequential(
        self,
        urls: list[str],
        delay: float = 1.0,
        max_retries: int = 5,
        max_backoff: float = 32.0,
        on_retry: Callable[[str, int, int | None], None] | None = None,
    ) -> Iterator[tuple[ScrapeResult, bool, int]]:
        """Scrape URLs sequentially with retry logic for transient errors.

        This method processes URLs one at a time, implementing exponential backoff
        for retryable errors (429, 5xx, network errors) while immediately failing
        on permanent errors (4xx except 408/429).

        Args:
            urls: List of URLs to scrape
            delay: Maximum delay in seconds between requests (actual delay is random 0 to delay)
            max_retries: Maximum retry attempts for retryable errors
            max_backoff: Maximum backoff delay in seconds
            on_retry: Optional callback(url, attempt, status_code) called on each retry

        Yields:
            Tuple of (ScrapeResult, is_permanent_error, retry_count)
            - ScrapeResult: The scrape result (success or failure)
            - is_permanent_error: True if error is permanent (no point retrying later)
            - retry_count: Number of retries attempted (0 = succeeded first try)
        """
        for i, url in enumerate(urls):
            result: ScrapeResult | None = None
            permanent = False
            retry_count = 0

            for attempt in range(max_retries + 1):
                result = self.scrape_url(url)

                # Check if successful (2xx status code)
                if result.success:
                    break

                # Check if permanent error (4xx except 408, 429)
                if is_permanent_error(result.status_code):
                    permanent = True
                    break

                # Retryable error - apply backoff if we have retries left
                if attempt < max_retries:
                    retry_count = attempt + 1
                    backoff = min(1.0 * (2 ** attempt), max_backoff)
                    if on_retry:
                        on_retry(url, retry_count, result.status_code)
                    time.sleep(backoff)
                # else: exhausted retries, will yield the failed result

            # Yield the result
            if result is not None:
                yield result, permanent, retry_count

            # Random politeness delay before next URL (but not after the last one)
            if i < len(urls) - 1 and delay > 0:
                time.sleep(random.uniform(0, delay))
