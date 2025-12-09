"""Binance fetcher with USDT/USD conversion.

Binance primarily offers USDT pairs. This fetcher:
1. Fetches BASE/USDT from Binance
2. Reads USDT/USD rate from shared cache (populated by PriceOracle)
3. Returns the USD-equivalent price

Endpoint: https://api.binance.com/api/v3/ticker/price
Rate Limit: High (no key required for public endpoints)
ROSE Support: Yes (via USDT pair)
"""

import logging

from ..usdt_rate_cache import UsdtRateCache
from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class BinanceFetcher(BaseFetcher):
    """Fetcher for Binance with USDT to USD conversion.

    For /usd quotes, fetches the USDT pair and converts using
    the USDT/USD rate from the shared cache (populated by PriceOracle
    from usdt/usd aggregation).

    Includes USDT depeg detection - if USDT deviates >2% from 1.0,
    the source is excluded.
    """

    name = "binance"
    BASE_URL = "https://api.binance.com/api/v3"

    # USDT depeg threshold (2%)
    USDT_DEPEG_THRESHOLD = 0.02

    def supports_pair(self, base: str, quote: str) -> bool:
        """Check if pair is supported.

        Binance cannot provide USDT/USD because it would be USDT/USDT.
        This also prevents circular dependency in usdt/usd aggregation.

        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: True if pair is supported.
        """
        return base.lower() != "usdt"

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from Binance.

        For USD quotes, fetches USDT pair and converts.

        :param base: Base currency (e.g., "btc", "eth", "rose").
        :param quote: Quote currency (e.g., "usd", "usdt").
        :returns: Current price or None on failure.
        """
        # Determine if we need USDT conversion
        need_usdt_conversion = quote.lower() == "usd"
        actual_quote = "USDT" if need_usdt_conversion else quote.upper()

        symbol = f"{base.upper()}{actual_quote}"
        url = f"{self.BASE_URL}/ticker/price"

        try:
            response = await self._get(url, params={"symbol": symbol})
            data = response.json()

            if "price" not in data:
                logger.warning(f"[binance] No price for {symbol}: {data}")
                return None

            price = float(data["price"])

            # Convert USDT to USD if needed
            if need_usdt_conversion:
                usdt_rate = await self._get_usdt_rate()
                if usdt_rate is None:
                    logger.warning("[binance] Failed to get USDT/USD rate")
                    return None

                # Check for USDT depeg
                if abs(usdt_rate - 1.0) > self.USDT_DEPEG_THRESHOLD:
                    logger.warning(
                        f"[binance] USDT depeg detected: rate={usdt_rate:.4f}. "
                        "Excluding from aggregation."
                    )
                    return None

                price = price * usdt_rate

            return price

        except FetcherError as e:
            logger.warning(f"[binance] Failed to fetch {symbol}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[binance] Failed to parse response: {e}")
            return None

    async def _get_usdt_rate(self) -> float | None:
        """Get USDT/USD rate from shared cache.

        The rate is populated by PriceOracle from the usdt/usd aggregation
        (fetched from CoinGecko, Kraken, Yahoo, etc.).

        :returns: USDT/USD rate or None if cache is empty/stale.
        """
        rate = UsdtRateCache.get()
        if rate is None:
            logger.warning(
                "[binance] No USDT/USD rate available in cache. "
                "Ensure usdt/usd pair is being tracked."
            )
        return rate

    @property
    def supports_batch(self) -> bool:
        """Binance supports batch fetching multiple symbols in one request."""
        return True

    async def fetch_batch(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], float | None]:
        """Fetch prices for multiple pairs in a single API call.

        Binance's /ticker/price endpoint accepts a symbols array parameter
        for batch queries. USD pairs are converted via USDT.

        :param pairs: List of (base, quote) tuples to fetch.
        :returns: Dict mapping (base, quote) to price or None.
        """
        import json

        results: dict[tuple[str, str], float | None] = {}

        # Filter out unsupported pairs (usdt/usd)
        supported_pairs: list[tuple[str, str]] = []
        for base, quote in pairs:
            if not self.supports_pair(base, quote):
                results[(base, quote)] = None
            else:
                supported_pairs.append((base, quote))

        if not supported_pairs:
            return results

        # Check if any pairs need USDT conversion
        needs_usdt_conversion = any(q.lower() == "usd" for _, q in supported_pairs)
        usdt_rate: float | None = None
        if needs_usdt_conversion:
            usdt_rate = await self._get_usdt_rate()
            if usdt_rate is None:
                # Can't convert, mark all USD pairs as failed
                for base, quote in supported_pairs:
                    if quote.lower() == "usd":
                        results[(base, quote)] = None
                # Filter to non-USD pairs only
                supported_pairs = [
                    (b, q) for b, q in supported_pairs if q.lower() != "usd"
                ]
                if not supported_pairs:
                    return results
            elif abs(usdt_rate - 1.0) > self.USDT_DEPEG_THRESHOLD:
                logger.warning(
                    f"[binance] USDT depeg detected: rate={usdt_rate:.4f}. "
                    "Excluding all USD pairs from batch."
                )
                for base, quote in supported_pairs:
                    if quote.lower() == "usd":
                        results[(base, quote)] = None
                supported_pairs = [
                    (b, q) for b, q in supported_pairs if q.lower() != "usd"
                ]
                if not supported_pairs:
                    return results

        # Build symbols list - convert USD to USDT for Binance
        symbols: list[str] = []
        symbol_to_pair: dict[str, tuple[str, str]] = {}
        for base, quote in supported_pairs:
            actual_quote = "USDT" if quote.lower() == "usd" else quote.upper()
            symbol = f"{base.upper()}{actual_quote}"
            symbols.append(symbol)
            symbol_to_pair[symbol] = (base, quote)

        url = f"{self.BASE_URL}/ticker/price"

        try:
            # Binance expects symbols as JSON array string
            response = await self._get(url, params={"symbols": json.dumps(symbols)})
            data = response.json()

            # Parse response - returns list of {symbol, price}
            price_map: dict[str, float] = {}
            for item in data:
                if "symbol" in item and "price" in item:
                    price_map[item["symbol"]] = float(item["price"])

            # Map results back to original pairs
            for symbol, (base, quote) in symbol_to_pair.items():
                if symbol not in price_map:
                    results[(base, quote)] = None
                    continue

                price = price_map[symbol]

                # Apply USDT conversion if needed
                if quote.lower() == "usd" and usdt_rate is not None:
                    price = price * usdt_rate

                results[(base, quote)] = price

        except FetcherError as e:
            logger.warning(f"[binance] Batch fetch failed: {e}")
            for base, quote in supported_pairs:
                if (base, quote) not in results:
                    results[(base, quote)] = None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[binance] Failed to parse batch response: {e}")
            for base, quote in supported_pairs:
                if (base, quote) not in results:
                    results[(base, quote)] = None

        return results
