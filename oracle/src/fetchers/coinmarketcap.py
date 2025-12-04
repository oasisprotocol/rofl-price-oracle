"""CoinMarketCap fetcher.

Endpoint: https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest
Rate Limit: 333 calls/day (free tier)
ROSE Support: Yes
API Key: Required
"""

import logging

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class CoinMarketCapFetcher(BaseFetcher):
    """Fetcher for CoinMarketCap API.

    Supports all major cryptocurrencies including ROSE/USD.
    Free tier: 333 calls/day.
    API key is REQUIRED.
    """

    name = "coinmarketcap"
    BASE_URL = "https://pro-api.coinmarketcap.com"

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from CoinMarketCap.

        :param base: Base currency (e.g., "btc", "eth", "rose").
        :param quote: Quote currency (e.g., "usd").
        :returns: Current price or None on failure.
        """
        if not self.api_key:
            logger.warning("[coinmarketcap] API key required but not provided")
            return None

        url = f"{self.BASE_URL}/v2/cryptocurrency/quotes/latest"
        headers = {"X-CMC_PRO_API_KEY": self.api_key}
        params = {"symbol": base.upper(), "convert": quote.upper()}

        try:
            response = await self._get(url, params=params, headers=headers)
            data = response.json()

            if "data" not in data:
                logger.warning(f"[coinmarketcap] No data in response: {data}")
                return None

            symbol_data = data["data"].get(base.upper())
            if not symbol_data:
                logger.warning(f"[coinmarketcap] Symbol {base.upper()} not found")
                return None

            # CMC returns a list of matches, take the first one
            if isinstance(symbol_data, list):
                symbol_data = symbol_data[0]

            quote_data = symbol_data.get("quote", {}).get(quote.upper())
            if not quote_data:
                logger.warning(
                    f"[coinmarketcap] Quote {quote.upper()} not found for {base.upper()}"
                )
                return None

            return float(quote_data["price"])

        except FetcherError as e:
            logger.warning(f"[coinmarketcap] Failed to fetch {base}/{quote}: {e}")
            return None
        except (KeyError, ValueError, TypeError, IndexError) as e:
            logger.warning(f"[coinmarketcap] Failed to parse response: {e}")
            return None
