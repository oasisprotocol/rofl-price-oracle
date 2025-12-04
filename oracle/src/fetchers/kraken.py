"""Kraken fetcher.

Endpoint: https://api.kraken.com/0/public/Ticker?pair={BASE}{QUOTE}
Rate Limit: High (no key required)
ROSE Support: No (API returns "Unknown asset pair")
"""

import logging

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class KrakenFetcher(BaseFetcher):
    """Fetcher for Kraken public API.

    Supports major USD pairs (BTC, ETH, etc.) but NOT ROSE.
    No API key required.
    """

    name = "kraken"
    BASE_URL = "https://api.kraken.com/0/public"

    # Kraken uses non-standard ticker symbols
    SYMBOL_MAP = {
        "btc": "XBT",  # Kraken uses XBT instead of BTC
    }

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from Kraken.

        :param base: Base currency (e.g., "btc", "eth").
        :param quote: Quote currency (e.g., "usd").
        :returns: Current price or None on failure.
        """
        # Map common symbols to Kraken's format
        kraken_base = self.SYMBOL_MAP.get(base.lower(), base.upper())
        kraken_quote = quote.upper()
        pair = f"{kraken_base}{kraken_quote}"

        url = f"{self.BASE_URL}/Ticker"

        try:
            response = await self._get(url, params={"pair": pair})
            data = response.json()

            # Check for errors
            if data.get("error"):
                errors = data["error"]
                if errors:
                    logger.warning(f"[kraken] API error for {pair}: {errors}")
                    return None

            result = data.get("result", {})
            if not result:
                logger.warning(f"[kraken] No result for {pair}")
                return None

            # Kraken returns results with pair names as keys (may vary slightly)
            pair_data = list(result.values())[0]

            # 'c' is the last trade closed array: [price, lot volume]
            price = pair_data["c"][0]
            return float(price)

        except FetcherError as e:
            logger.warning(f"[kraken] Failed to fetch {pair}: {e}")
            return None
        except (KeyError, ValueError, TypeError, IndexError) as e:
            logger.warning(f"[kraken] Failed to parse response for {pair}: {e}")
            return None

    def supports_pair(self, base: str, quote: str) -> bool:
        """Check if pair is supported (Kraken doesn't support ROSE).

        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: True if pair is supported.
        """
        return base.lower() != "rose"
