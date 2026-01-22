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

    async def supports_pair(self, base: str, quote: str) -> bool:
        """Check if pair is supported (Kraken doesn't support ROSE).

        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: True if pair is supported.
        """
        return base.lower() != "rose"

    @property
    def supports_batch(self) -> bool:
        """Kraken supports batch fetching multiple pairs."""
        return True

    async def fetch_batch(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], float | None]:
        """Fetch prices for multiple pairs in a single API call.

        Kraken's /Ticker endpoint accepts comma-separated pairs
        for efficient batch queries.

        :param pairs: List of (base, quote) tuples to fetch.
        :returns: Dict mapping (base, quote) to price or None.
        """
        results: dict[tuple[str, str], float | None] = {}

        if not pairs:
            return results

        # Filter to supported pairs and build Kraken symbols
        supported_pairs: list[tuple[str, str]] = []
        kraken_pairs: list[str] = []
        pair_to_kraken: dict[tuple[str, str], str] = {}

        for base, quote in pairs:
            if not self.supports_pair(base, quote):
                results[(base, quote)] = None
                continue

            # Map common symbols to Kraken's format
            kraken_base = self.SYMBOL_MAP.get(base.lower(), base.upper())
            kraken_quote = quote.upper()
            kraken_pair = f"{kraken_base}{kraken_quote}"

            supported_pairs.append((base, quote))
            kraken_pairs.append(kraken_pair)
            pair_to_kraken[(base, quote)] = kraken_pair

        if not supported_pairs:
            return results

        url = f"{self.BASE_URL}/Ticker"

        try:
            response = await self._get(url, params={"pair": ",".join(kraken_pairs)})
            data = response.json()

            # Check for errors
            if data.get("error"):
                errors = data["error"]
                if errors:
                    logger.warning(f"[kraken] Batch API error: {errors}")
                    for base, quote in supported_pairs:
                        results[(base, quote)] = None
                    return results

            result_data = data.get("result", {})
            if not result_data:
                logger.warning("[kraken] No result in batch response")
                for base, quote in supported_pairs:
                    results[(base, quote)] = None
                return results

            # Map results back to original pairs
            # Kraken returns results with pair names as keys (may vary slightly)
            for base, quote in supported_pairs:
                kraken_pair = pair_to_kraken[(base, quote)]

                # Kraken might use different key formats, try exact match first
                pair_data = result_data.get(kraken_pair)

                # If not found, try to find a matching key
                if pair_data is None:
                    for key in result_data:
                        # Kraken sometimes prefixes with X or Z
                        normalized = key.replace("X", "").replace("Z", "")
                        if kraken_pair in key or normalized == kraken_pair:
                            pair_data = result_data[key]
                            break

                if pair_data is None:
                    results[(base, quote)] = None
                    continue

                # 'c' is the last trade closed array: [price, lot volume]
                price = pair_data.get("c", [None])[0]
                if price is None:
                    results[(base, quote)] = None
                    continue

                results[(base, quote)] = float(price)

        except FetcherError as e:
            logger.warning(f"[kraken] Batch fetch failed: {e}")
            for base, quote in supported_pairs:
                results[(base, quote)] = None
        except (KeyError, ValueError, TypeError, IndexError) as e:
            logger.warning(f"[kraken] Failed to parse batch response: {e}")
            for base, quote in supported_pairs:
                results[(base, quote)] = None

        return results
