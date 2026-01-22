"""CoinAPI fetcher.

Endpoint: https://rest.coinapi.io/v1/exchangerate/{BASE}/{QUOTE}
Rate Limit: Varies by plan ($25 free credits, then paid)
ROSE Support: Yes
API Key: Required
"""

import logging

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class CoinAPIFetcher(BaseFetcher):
    """Fetcher for CoinAPI.

    Professional-grade API with 400+ exchanges.
    API key is REQUIRED.
    """

    name = "coinapi"
    BASE_URL = "https://rest.coinapi.io/v1"

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from CoinAPI.

        :param base: Base currency (e.g., "btc", "eth", "rose").
        :param quote: Quote currency (e.g., "usd").
        :returns: Current price or None on failure.
        """
        if not self.api_key:
            logger.warning("[coinapi] API key required but not provided")
            return None

        url = f"{self.BASE_URL}/exchangerate/{base.upper()}/{quote.upper()}"
        headers = {"X-CoinAPI-Key": self.api_key}

        try:
            response = await self._get(url, headers=headers)
            data = response.json()

            if "rate" not in data:
                logger.warning(f"[coinapi] No rate in response: {data}")
                return None

            return float(data["rate"])

        except FetcherError as e:
            logger.warning(f"[coinapi] Failed to fetch {base}/{quote}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[coinapi] Failed to parse response: {e}")
            return None
