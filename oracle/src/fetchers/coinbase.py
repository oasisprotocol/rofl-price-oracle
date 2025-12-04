"""Coinbase Exchange fetcher.

Endpoint: https://api.exchange.coinbase.com/products/{BASE}-{QUOTE}/ticker
Rate Limit: High (no key required)
ROSE Support: Yes
"""

import logging

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class CoinbaseFetcher(BaseFetcher):
    """Fetcher for Coinbase Exchange API.

    Supports native USD pairs including ROSE/USD.
    No API key required for public ticker endpoint.
    """

    name = "coinbase"
    BASE_URL = "https://api.exchange.coinbase.com"

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from Coinbase Exchange.

        :param base: Base currency (e.g., "btc", "eth", "rose").
        :param quote: Quote currency (e.g., "usd").
        :returns: Current price or None on failure.
        """
        symbol = f"{base.upper()}-{quote.upper()}"
        url = f"{self.BASE_URL}/products/{symbol}/ticker"

        try:
            response = await self._get(url)
            data = response.json()

            if "price" not in data:
                logger.warning(f"[coinbase] No price in response for {symbol}: {data}")
                return None

            return float(data["price"])

        except FetcherError as e:
            logger.warning(f"[coinbase] Failed to fetch {symbol}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[coinbase] Failed to parse response for {symbol}: {e}")
            return None
