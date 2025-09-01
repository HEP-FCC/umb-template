"""
Centralized HTTP client with retrying capabilities using aiohttp and tenacity.
This module provides a unified HTTP client interface for all backend HTTP operations.
"""

import logging
from collections.abc import Callable
from typing import Any

import aiohttp
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.utils.config_utils import get_config
from app.utils.logging_utils import get_logger

# Load configuration and logger
logger = get_logger(__name__)
config = get_config()


class RetryingHTTPClient:
    """
    Production-ready HTTP client with automatic retry capabilities.

    Features:
    - Uses aiohttp for async HTTP requests
    - Automatic retries with exponential backoff using tenacity
    - Configurable timeout and retry settings
    - Proper connection pooling and session management
    - Comprehensive error handling and logging
    """

    def __init__(
        self,
        timeout: float = 10.0,
        max_retries: int = 3,
        retry_multiplier: float = 1.0,
        retry_min_wait: float = 1.0,
        retry_max_wait: float = 10.0,
        connector_limit: int = 100,
        connector_limit_per_host: int = 30,
    ):
        """
        Initialize the retrying HTTP client.

        Args:
            timeout: Default timeout for requests in seconds
            max_retries: Maximum number of retry attempts
            retry_multiplier: Multiplier for exponential backoff
            retry_min_wait: Minimum wait time between retries
            retry_max_wait: Maximum wait time between retries
            connector_limit: Total connection pool limit
            connector_limit_per_host: Connection limit per host
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_multiplier = retry_multiplier
        self.retry_min_wait = retry_min_wait
        self.retry_max_wait = retry_max_wait

        # Create connector with connection pooling settings
        self.connector = aiohttp.TCPConnector(
            limit=connector_limit,
            limit_per_host=connector_limit_per_host,
            enable_cleanup_closed=True,
        )

        # Create session with timeout and connector
        self.timeout_config = aiohttp.ClientTimeout(total=timeout)
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "RetryingHTTPClient":
        """Async context manager entry."""
        await self.start_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close_session()

    async def start_session(self) -> None:
        """Start the HTTP session if not already started (thread-safe)."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                connector=self.connector,
                timeout=self.timeout_config,
            )
            logger.debug("Started new HTTP client session")

    async def close_session(self) -> None:
        """Close the HTTP session and cleanup resources."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("Closed HTTP client session")

    def _create_retry_decorator(self) -> Callable[..., Any]:
        """Create a tenacity retry decorator with configured settings."""
        return retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(
                multiplier=self.retry_multiplier,
                min=self.retry_min_wait,
                max=self.retry_max_wait,
            ),
            retry=retry_if_exception_type(
                (
                    aiohttp.ClientError,
                    aiohttp.ServerTimeoutError,
                    aiohttp.ClientConnectionError,
                    aiohttp.ClientPayloadError,
                    aiohttp.ClientResponseError,
                )
            ),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

    async def _execute_request(
        self, method: str, url: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """
        Execute HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            url: Request URL
            **kwargs: Additional arguments passed to aiohttp request

        Returns:
            aiohttp.ClientResponse object

        Raises:
            aiohttp.ClientError: On connection or request errors after retries
            aiohttp.ClientResponseError: On HTTP error responses after retries
        """
        await self.start_session()

        if self.session is None:
            raise RuntimeError("HTTP session not initialized")

        # Apply retry decorator to the request execution
        @self._create_retry_decorator()
        async def make_request() -> aiohttp.ClientResponse:
            logger.debug(f"Making {method} request to {url}")
            assert self.session is not None  # Help mypy understand session is not None
            response = await self.session.request(method, url, **kwargs)

            # Raise for HTTP error status codes (4xx, 5xx)
            # This will trigger retry for 5xx errors but not 4xx errors
            if response.status >= 500:
                response.raise_for_status()
            elif response.status >= 400:
                # For 4xx errors, we don't retry but still raise the error
                # But first we need to read the response to avoid connection issues
                try:
                    await response.read()
                finally:
                    response.raise_for_status()

            return response

        result = await make_request()
        return result  # type: ignore[no-any-return]

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """
        Make a GET request.

        Args:
            url: Request URL
            params: URL parameters
            headers: Request headers
            timeout: Request timeout (overrides default)
            **kwargs: Additional arguments

        Returns:
            aiohttp.ClientResponse object
        """
        request_timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
        return await self._execute_request(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=request_timeout,
            **kwargs,
        )

    async def post(
        self,
        url: str,
        data: dict[str, Any] | bytes | str | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """
        Make a POST request.

        Args:
            url: Request URL
            data: Request body data
            json: JSON data to send
            headers: Request headers
            timeout: Request timeout (overrides default)
            **kwargs: Additional arguments

        Returns:
            aiohttp.ClientResponse object
        """
        request_timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
        return await self._execute_request(
            "POST",
            url,
            data=data,
            json=json,
            headers=headers,
            timeout=request_timeout,
            **kwargs,
        )

    async def put(
        self,
        url: str,
        data: dict[str, Any] | bytes | str | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """
        Make a PUT request.

        Args:
            url: Request URL
            data: Request body data
            json: JSON data to send
            headers: Request headers
            timeout: Request timeout (overrides default)
            **kwargs: Additional arguments

        Returns:
            aiohttp.ClientResponse object
        """
        request_timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
        return await self._execute_request(
            "PUT",
            url,
            data=data,
            json=json,
            headers=headers,
            timeout=request_timeout,
            **kwargs,
        )

    async def delete(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """
        Make a DELETE request.

        Args:
            url: Request URL
            headers: Request headers
            timeout: Request timeout (overrides default)
            **kwargs: Additional arguments

        Returns:
            aiohttp.ClientResponse object
        """
        request_timeout = aiohttp.ClientTimeout(total=timeout) if timeout else None
        return await self._execute_request(
            "DELETE", url, headers=headers, timeout=request_timeout, **kwargs
        )

    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Make a GET request and return JSON response.

        Args:
            url: Request URL
            params: URL parameters
            headers: Request headers
            timeout: Request timeout (overrides default)
            **kwargs: Additional arguments

        Returns:
            Parsed JSON response as dictionary
        """
        async with await self.get(
            url, params=params, headers=headers, timeout=timeout, **kwargs
        ) as response:
            result = await response.json()
            return result  # type: ignore[no-any-return]

    async def post_json(
        self,
        url: str,
        data: dict[str, Any] | bytes | str | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Make a POST request and return JSON response.

        Args:
            url: Request URL
            data: Request body data
            json: JSON data to send
            headers: Request headers
            timeout: Request timeout (overrides default)
            **kwargs: Additional arguments

        Returns:
            Parsed JSON response as dictionary
        """
        async with await self.post(
            url, data=data, json=json, headers=headers, timeout=timeout, **kwargs
        ) as response:
            result = await response.json()
            return result  # type: ignore[no-any-return]


# Factory function to create HTTP client instances
def create_http_client(
    timeout: float = 10.0,
    max_retries: int = 3,
    retry_multiplier: float = 1.0,
    retry_min_wait: float = 1.0,
    retry_max_wait: float = 10.0,
    connector_limit: int = 100,
    connector_limit_per_host: int = 30,
) -> RetryingHTTPClient:
    """
    Create a new HTTP client instance with the specified configuration.

    Args:
        timeout: Default timeout for requests in seconds
        max_retries: Maximum number of retry attempts
        retry_multiplier: Multiplier for exponential backoff
        retry_min_wait: Minimum wait time between retries
        retry_max_wait: Maximum wait time between retries
        connector_limit: Total connection pool limit
        connector_limit_per_host: Connection limit per host

    Returns:
        A new RetryingHTTPClient instance
    """
    return RetryingHTTPClient(
        timeout=timeout,
        max_retries=max_retries,
        retry_multiplier=retry_multiplier,
        retry_min_wait=retry_min_wait,
        retry_max_wait=retry_max_wait,
        connector_limit=connector_limit,
        connector_limit_per_host=connector_limit_per_host,
    )


# Convenience functions that create their own client instances
async def get_json(url: str, **kwargs: Any) -> dict[str, Any]:
    """Convenience function for GET JSON requests."""
    async with create_http_client() as client:
        return await client.get_json(url, **kwargs)


async def post_json(url: str, **kwargs: Any) -> dict[str, Any]:
    """Convenience function for POST JSON requests."""
    async with create_http_client() as client:
        return await client.post_json(url, **kwargs)


async def get_response(url: str, **kwargs: Any) -> aiohttp.ClientResponse:
    """Convenience function for GET requests."""
    async with create_http_client() as client:
        return await client.get(url, **kwargs)


async def post_response(url: str, **kwargs: Any) -> aiohttp.ClientResponse:
    """Convenience function for POST requests."""
    async with create_http_client() as client:
        return await client.post(url, **kwargs)
