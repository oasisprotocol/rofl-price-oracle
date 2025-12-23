"""CoinGecko fetcher.

Endpoint: https://api.coingecko.com/api/v3/simple/price?ids={id}&vs_currencies={quote}
Rate Limit: 30 calls/min (free), higher with API key
ROSE Support: Yes (id: "oasis-network")
"""

import logging

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class CoinGeckoFetcher(BaseFetcher):
    """Fetcher for CoinGecko API.

    Supports all major cryptocurrencies including ROSE/USD.

    API tiers:
        - Free: api.coingecko.com (no key, 30 calls/min)
        - Demo: api.coingecko.com + x-cg-demo-api-key header
        - Pro: pro-api.coingecko.com + x-cg-pro-api-key header

    To use a demo key, prefix with "demo:": API_KEY_COINGECKO=demo:CG-xxxxx
    Pro keys need no prefix: API_KEY_COINGECKO=xxxxx
    """

    name = "coingecko"
    BASE_URL_FREE = "https://api.coingecko.com/api/v3"
    BASE_URL_PRO = "https://pro-api.coingecko.com/api/v3"

    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        """Initialize with optional demo: prefix handling."""
        self._is_demo = False
        if api_key and api_key.lower().startswith("demo:"):
            self._is_demo = True
            api_key = api_key[5:]  # Strip "demo:" prefix
        super().__init__(api_key=api_key, timeout=timeout)

    @property
    def base_url(self) -> str:
        """Return appropriate base URL based on API key type."""
        if not self.has_api_key:
            return self.BASE_URL_FREE
        # Demo keys use free URL, pro keys use pro URL
        return self.BASE_URL_FREE if self._is_demo else self.BASE_URL_PRO

    @property
    def api_header(self) -> tuple[str, str] | None:
        """Return appropriate header name and value for API key."""
        if not self.api_key:
            return None
        header_name = "x-cg-demo-api-key" if self._is_demo else "x-cg-pro-api-key"
        return (header_name, self.api_key)

    # Map common symbols to CoinGecko IDs
    COIN_IDS = {
        "btc": "bitcoin",
        "eth": "ethereum",
        "rose": "oasis-network",
        "usdt": "tether",
        "usdc": "usd-coin",
        "sol": "solana",
        "avax": "avalanche-2",
        "matic": "matic-network",
        "dot": "polkadot",
        "atom": "cosmos",
        "link": "chainlink",
        "uni": "uniswap",
        "aave": "aave",
    }

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from CoinGecko.

        :param base: Base currency (e.g., "btc", "eth", "rose").
        :param quote: Quote currency (e.g., "usd").
        :returns: Current price or None on failure.
        """
        coin_id = self.COIN_IDS.get(base.lower())
        if not coin_id:
            logger.warning(f"[coingecko] Unknown coin: {base}")
            return None

        quote_lower = quote.lower()
        url = f"{self.base_url}/simple/price"

        headers = {}
        if self.api_header:
            header_name, header_value = self.api_header
            headers[header_name] = header_value

        try:
            response = await self._get(
                url,
                params={"ids": coin_id, "vs_currencies": quote_lower},
                headers=headers if headers else None,
            )
            data = response.json()

            if coin_id not in data:
                logger.warning(f"[coingecko] Coin {coin_id} not in response: {data}")
                return None

            if quote_lower not in data[coin_id]:
                logger.warning(
                    f"[coingecko] Quote {quote_lower} not available for {coin_id}"
                )
                return None

            return float(data[coin_id][quote_lower])

        except FetcherError as e:
            logger.warning(f"[coingecko] Failed to fetch {base}/{quote}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[coingecko] Failed to parse response: {e}")
            return None

    async def supports_pair(self, base: str, quote: str) -> bool:
        """Check if pair is supported (base must be in COIN_IDS).

        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: True if pair is supported.
        """
        return base.lower() in self.COIN_IDS

    @property
    def supports_batch(self) -> bool:
        """CoinGecko supports batch fetching multiple coins in one request."""
        return True

    async def fetch_batch(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], float | None]:
        """Fetch prices for multiple pairs in a single API call.

        CoinGecko's /simple/price endpoint accepts comma-separated coin IDs
        and vs_currencies, allowing efficient batch queries.

        :param pairs: List of (base, quote) tuples to fetch.
        :returns: Dict mapping (base, quote) to price or None.
        """
        results: dict[tuple[str, str], float | None] = {}

        # Filter to supported pairs and build lookup maps
        coin_id_to_bases: dict[str, list[str]] = {}  # coin_id -> [base symbols]
        quotes: set[str] = set()

        for base, quote in pairs:
            coin_id = self.COIN_IDS.get(base.lower())
            if not coin_id:
                results[(base, quote)] = None
                continue

            if coin_id not in coin_id_to_bases:
                coin_id_to_bases[coin_id] = []
            coin_id_to_bases[coin_id].append(base.lower())
            quotes.add(quote.lower())

        if not coin_id_to_bases:
            return results

        # Build request
        url = f"{self.base_url}/simple/price"
        headers = {}
        if self.api_header:
            header_name, header_value = self.api_header
            headers[header_name] = header_value

        try:
            response = await self._get(
                url,
                params={
                    "ids": ",".join(coin_id_to_bases.keys()),
                    "vs_currencies": ",".join(quotes),
                },
                headers=headers if headers else None,
            )
            data = response.json()

            # Map results back to original pairs
            for base, quote in pairs:
                coin_id = self.COIN_IDS.get(base.lower())
                if not coin_id or coin_id not in data:
                    results[(base, quote)] = None
                    continue

                quote_lower = quote.lower()
                if quote_lower not in data[coin_id]:
                    results[(base, quote)] = None
                    continue

                results[(base, quote)] = float(data[coin_id][quote_lower])

        except FetcherError as e:
            logger.warning(f"[coingecko] Batch fetch failed: {e}")
            # Mark all pairs as failed
            for base, quote in pairs:
                if (base, quote) not in results:
                    results[(base, quote)] = None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[coingecko] Failed to parse batch response: {e}")
            for base, quote in pairs:
                if (base, quote) not in results:
                    results[(base, quote)] = None

        return results
