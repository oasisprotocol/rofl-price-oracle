"""Bitstamp fetcher.

Endpoint: https://www.bitstamp.net/api/v2/ticker/{base}{quote}/
Rate Limit: High (no key required)
ROSE Support: No
"""

import logging

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class BitstampFetcher(BaseFetcher):
    """Fetcher for Bitstamp public API.

    Supports major USD pairs (BTC, ETH, etc.) but NOT ROSE.
    No API key required.
    """

    name = "bitstamp"
    BASE_URL = "https://www.bitstamp.net/api/v2"

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from Bitstamp.

        :param base: Base currency (e.g., "btc", "eth").
        :param quote: Quote currency (e.g., "usd").
        :returns: Current price or None on failure.
        """
        pair = f"{base.lower()}{quote.lower()}"
        url = f"{self.BASE_URL}/ticker/{pair}/"

        try:
            response = await self._get(url)
            data = response.json()

            if "last" not in data:
                logger.warning(f"[bitstamp] No 'last' price for {pair}: {data}")
                return None

            return float(data["last"])

        except FetcherError as e:
            logger.warning(f"[bitstamp] Failed to fetch {pair}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[bitstamp] Failed to parse response for {pair}: {e}")
            return None

    def supports_pair(self, base: str, quote: str) -> bool:
        """Check if pair is supported (Bitstamp doesn't support ROSE).

        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: True if pair is supported.
        """
        return base.lower() != "rose"
