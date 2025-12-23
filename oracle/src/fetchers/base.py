"""Base fetcher interface and shared HTTP client management.

All price fetchers inherit from BaseFetcher and implement the fetch() method.
A shared httpx.AsyncClient is used across all fetchers to avoid connection overhead.

Fetchers can optionally implement batch fetching for APIs that support querying
multiple pairs in a single request, reducing API calls significantly.

.. code-block:: python

    @register_fetcher
    class MyFetcher(BaseFetcher):
        name = "myfetcher"

        async def fetch(self, base: str, quote: str) -> float | None:
            response = await self._get(f"https://api.example.com/{base}/{quote}")
            return response.json()["price"]

        # Optional: implement for batch-capable APIs
        @property
        def supports_batch(self) -> bool:
            return True

        async def fetch_batch(
            self, pairs: list[tuple[str, str]]
        ) -> dict[tuple[str, str], float | None]:
            # Fetch multiple pairs in one API call
            ...
"""

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

import httpx

logger = logging.getLogger(__name__)


class FetcherError(Exception):
    """Base exception for fetcher errors."""

    pass


class FetcherConfigError(FetcherError):
    """Raised when fetcher configuration is invalid (e.g., missing API key)."""

    pass


class FetcherHTTPError(FetcherError):
    """Raised when HTTP request fails.

    :ivar status_code: HTTP status code from the failed request.
    """

    def __init__(self, status_code: int, message: str):
        """Initialize the HTTP error.

        :param status_code: HTTP status code.
        :param message: Error message from response.
        """
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


class BaseFetcher(ABC):
    """Abstract base class for price fetchers.

    Subclasses must implement:
        - name: Class variable identifying the source (e.g., "coinbase", "kraken")
        - fetch(): Async method to fetch price for a trading pair

    :cvar name: Unique identifier for this fetcher.
    :cvar DEFAULT_TIMEOUT: Default HTTP request timeout in seconds.
    :ivar api_key: Optional API key for authenticated endpoints.
    :ivar timeout: Request timeout in seconds.
    """

    # Class-level shared HTTP client
    _shared_client: ClassVar[httpx.AsyncClient | None] = None

    # Fetcher identification
    name: ClassVar[str] = ""

    # Default timeout for HTTP requests (seconds)
    DEFAULT_TIMEOUT = 10.0

    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        """Initialize the fetcher.

        :param api_key: Optional API key for authenticated endpoints.
        :param timeout: Request timeout in seconds (default: 10).
        """
        self.api_key = api_key
        self.timeout = timeout or self.DEFAULT_TIMEOUT

    @property
    def has_api_key(self) -> bool:
        """Check if this fetcher has an API key configured."""
        return self.api_key is not None and len(self.api_key) > 0

    @classmethod
    def get_shared_client(cls) -> httpx.AsyncClient:
        """Get or create the shared HTTP client.

        The client is shared across all fetcher instances to reuse connections.

        :returns: Shared httpx.AsyncClient instance.
        """
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
                follow_redirects=True,
            )
        return cls._shared_client

    @classmethod
    async def close_shared_client(cls) -> None:
        """Close the shared HTTP client."""
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
            cls._shared_client = None

    @abstractmethod
    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch the current price for a trading pair.

        :param base: Base currency symbol (e.g., "btc", "eth", "rose").
        :param quote: Quote currency symbol (e.g., "usd").
        :returns: Current price as float, or None if fetch failed.
        """
        pass

    async def supports_pair(self, base: str, quote: str) -> bool:
        """Check if this fetcher supports the given trading pair.

        Override in subclasses to restrict supported pairs.
        Can make API calls if needed (e.g., to check symbol availability).

        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: True if pair is supported.
        """
        return True

    @property
    def supports_batch(self) -> bool:
        """Check if this fetcher supports batch fetching multiple pairs.

        Override in subclasses that implement fetch_batch() with actual
        batch API calls.

        :returns: True if batch fetching is supported.
        """
        return False

    async def fetch_batch(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], float | None]:
        """Fetch prices for multiple trading pairs.

        Default implementation falls back to sequential individual fetches.
        Override in subclasses to implement actual batch API calls.

        :param pairs: List of (base, quote) tuples to fetch.
        :returns: Dict mapping (base, quote) to price or None.
        """
        results: dict[tuple[str, str], float | None] = {}
        for base, quote in pairs:
            if await self.supports_pair(base, quote):
                results[(base, quote)] = await self.fetch(base, quote)
            else:
                results[(base, quote)] = None
        return results

    async def _get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        """Make an HTTP GET request using the shared client.

        :param url: Request URL.
        :param params: Optional query parameters.
        :param headers: Optional request headers.
        :returns: httpx.Response object.
        :raises FetcherHTTPError: On non-2xx response.
        :raises FetcherError: On network/timeout errors.
        """
        client = self.get_shared_client()
        try:
            response = await client.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            if not response.is_success:
                logger.debug(
                    "HTTP GET %s failed with status %s: %s",
                    url,
                    response.status_code,
                    response.text[:200],
                )
                raise FetcherHTTPError(response.status_code, response.text[:200])
            return response
        except httpx.TimeoutException as e:
            raise FetcherError(f"Request timeout: {e}") from e
        except httpx.RequestError as e:
            raise FetcherError(f"Request failed: {e}") from e

    async def _post(
        self,
        url: str,
        *,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        """Make an HTTP POST request using the shared client.

        :param url: Request URL.
        :param json: Optional JSON body.
        :param headers: Optional request headers.
        :returns: httpx.Response object.
        :raises FetcherHTTPError: On non-2xx response.
        :raises FetcherError: On network/timeout errors.
        """
        client = self.get_shared_client()
        try:
            response = await client.post(
                url,
                json=json,
                headers=headers,
                timeout=self.timeout,
            )
            if not response.is_success:
                logger.debug(
                    "HTTP POST %s failed with status %s: %s",
                    url,
                    response.status_code,
                    response.text[:200],
                )
                raise FetcherHTTPError(response.status_code, response.text[:200])
            return response
        except httpx.TimeoutException as e:
            raise FetcherError(f"Request timeout: {e}") from e
        except httpx.RequestError as e:
            raise FetcherError(f"Request failed: {e}") from e


# Registry of available fetchers (populated by subclass imports)
FETCHER_REGISTRY: dict[str, type[BaseFetcher]] = {}


def register_fetcher(cls: type[BaseFetcher]) -> type[BaseFetcher]:
    """Decorator to register a fetcher class in the global registry.

    :param cls: Fetcher class to register.
    :returns: The registered class (unchanged).
    :raises ValueError: If fetcher has no name defined.

    .. code-block:: python

        @register_fetcher
        class CoinbaseFetcher(BaseFetcher):
            name = "coinbase"
            ...
    """
    if not cls.name:
        raise ValueError(f"Fetcher {cls.__name__} must define a 'name' class variable")
    FETCHER_REGISTRY[cls.name] = cls
    return cls


def get_fetcher(name: str, api_key: str | None = None) -> BaseFetcher:
    """Get a fetcher instance by name.

    :param name: Fetcher name (e.g., "coinbase", "kraken").
    :param api_key: Optional API key.
    :returns: Fetcher instance.
    :raises ValueError: If fetcher name is unknown.
    """
    if name not in FETCHER_REGISTRY:
        available = ", ".join(sorted(FETCHER_REGISTRY.keys()))
        raise ValueError(f"Unknown fetcher '{name}'. Available: {available}")
    return FETCHER_REGISTRY[name](api_key=api_key)


def get_available_fetchers() -> list[str]:
    """Get list of available fetcher names.

    :returns: Sorted list of registered fetcher names.
    """
    return sorted(FETCHER_REGISTRY.keys())
