"""EODHD (End of Day Historical Data) fetcher.

Endpoint: https://eodhd.com/api/real-time/{SYM}-USD.CC
Rate Limit: ~100k calls/day (paid plans)
ROSE Support: Yes
API Key: Required
"""

import logging

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class EODHDFetcher(BaseFetcher):
    """Fetcher for EODHD API.

    Supports 2600+ USD pairs including cryptocurrencies.
    API key is REQUIRED.
    """

    name = "eodhd"
    BASE_URL = "https://eodhd.com/api"

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from EODHD.

        :param base: Base currency (e.g., "btc", "eth", "rose").
        :param quote: Quote currency (e.g., "usd").
        :returns: Current price or None on failure.
        """
        if not self.api_key:
            logger.warning("[eodhd] API key required but not provided")
            return None

        # Only USD quotes supported via this endpoint
        if quote.lower() != "usd":
            logger.warning(f"[eodhd] Only USD quotes supported, got {quote}")
            return None

        # EODHD uses {SYMBOL}-USD.CC format for crypto
        symbol = f"{base.upper()}-USD.CC"
        url = f"{self.BASE_URL}/real-time/{symbol}"

        try:
            response = await self._get(
                url, params={"api_token": self.api_key, "fmt": "json"}
            )
            data = response.json()

            # EODHD returns 'close' for the current price
            if "close" not in data:
                logger.warning(f"[eodhd] No 'close' in response: {data}")
                return None

            return float(data["close"])

        except FetcherError as e:
            logger.warning(f"[eodhd] Failed to fetch {base}/{quote}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[eodhd] Failed to parse response: {e}")
            return None

    async def supports_pair(self, base: str, quote: str) -> bool:
        """Check if pair is supported (EODHD only supports USD quotes).

        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: True if pair is supported.
        """
        return quote.lower() == "usd"
