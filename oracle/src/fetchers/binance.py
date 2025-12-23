"""Binance fetcher with self-contained USD conversion.

Binance offers USDT pairs for most assets. This fetcher:
1. For direct USD pairs (BTCUSD, USDTUSD, USDCUSD): fetch directly from Binance
2. For other /usd pairs: fetch BASE/USDT and USDT/USD in single request, multiply

No external dependencies for USD conversion - fully self-contained.

Endpoint: https://api.binance.com/api/v3/ticker/price
Rate Limit: High (no key required for public endpoints)
ROSE Support: Yes (via USDT pair + USDT/USD conversion)
"""

import json
import logging
from typing import ClassVar

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class BinanceFetcher(BaseFetcher):
    """Self-contained Binance fetcher with internal USD conversion.

    For /usd quotes, fetches the USDT pair and USDT/USD rate in a single
    API call, then multiplies. No external cache or fallback dependencies.

    Includes USDT depeg detection - if USDT deviates >2% from 1.0,
    the source is excluded.
    """

    name = "binance"
    BASE_URL = "https://api.binance.com/api/v3"

    # USDT depeg threshold (2%)
    USDT_DEPEG_THRESHOLD = 0.02

    # Per-pair fetch info: (symbol_to_fetch, needs_usdt_conversion)
    # e.g., ("btc", "usd") -> ("BTCUSD", False)  - direct pair
    # e.g., ("rose", "usd") -> ("ROSEUSDT", True)  - needs USDT conversion
    _pair_info: ClassVar[dict[tuple[str, str], tuple[str, bool]]] = {}

    async def supports_pair(self, base: str, quote: str) -> bool:
        """Check if pair is supported by querying Binance API.

        Also determines the fetch method (direct vs USDT conversion) and
        caches it for use by fetch().

        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: True if pair is supported.
        """
        key = (base.lower(), quote.lower())
        if key in self._pair_info:
            return True

        base_u = base.upper()
        quote_u = quote.upper()

        if quote_u == "USD":
            # Check direct USD pair and USDT conversion option
            direct = f"{base_u}USD"
            usdt = f"{base_u}USDT"
            prices = await self._fetch_symbols([direct, usdt, "USDTUSD"])

            if prices.get(direct) is not None:
                BinanceFetcher._pair_info[key] = (direct, False)
                return True
            if prices.get(usdt) is not None and prices.get("USDTUSD") is not None:
                BinanceFetcher._pair_info[key] = (usdt, True)
                return True
            return False

        # Non-USD quote - check direct pair
        symbol = f"{base_u}{quote_u}"
        prices = await self._fetch_symbols([symbol])
        if prices.get(symbol) is not None:
            BinanceFetcher._pair_info[key] = (symbol, False)
            return True
        return False

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from Binance.

        Uses fetch method determined by supports_pair() at startup.

        :param base: Base currency (e.g., "btc", "eth", "rose").
        :param quote: Quote currency (e.g., "usd", "usdt").
        :returns: Current price or None on failure.
        """
        info = self._pair_info.get((base.lower(), quote.lower()))
        if not info:
            logger.debug(f"[binance] Pair {base}/{quote} not in pair_info")
            return None

        symbol, needs_conversion = info

        if not needs_conversion:
            return await self._fetch_symbol(symbol)

        # USDT conversion needed
        price_map = await self._fetch_symbols([symbol, "USDTUSD"])
        usdt_price = price_map.get(symbol)
        usdt_rate = price_map.get("USDTUSD")

        if usdt_price is None or usdt_rate is None:
            logger.warning(
                f"[binance] Failed to get {symbol} or USDTUSD for conversion"
            )
            return None

        if self._is_depeg(usdt_rate):
            logger.warning(
                f"[binance] USDT depeg detected: rate={usdt_rate:.4f}. "
                "Excluding from aggregation."
            )
            return None

        return usdt_price * usdt_rate

    def _is_depeg(self, rate: float) -> bool:
        """Check if stablecoin has depegged (>2% from 1.0).

        :param rate: Stablecoin/USD rate.
        :returns: True if depegged beyond threshold.
        """
        return abs(rate - 1.0) > self.USDT_DEPEG_THRESHOLD

    async def _fetch_symbol(self, symbol: str) -> float | None:
        """Fetch price for a single symbol.

        :param symbol: Binance symbol (e.g., "BTCUSDT", "USDTUSD").
        :returns: Price or None on failure.
        """
        url = f"{self.BASE_URL}/ticker/price"
        try:
            response = await self._get(url, params={"symbol": symbol})
            data = response.json()
            if "price" not in data:
                logger.warning(f"[binance] No price for {symbol}: {data}")
                return None
            return float(data["price"])
        except FetcherError as e:
            logger.warning(f"[binance] Failed to fetch {symbol}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[binance] Failed to parse response for {symbol}: {e}")
            return None

    async def _fetch_symbols(self, symbols: list[str]) -> dict[str, float | None]:
        """Fetch prices for multiple symbols in a single API call.

        :param symbols: List of Binance symbols.
        :returns: Dict mapping symbol to price (or None if failed).
        """
        url = f"{self.BASE_URL}/ticker/price"
        try:
            response = await self._get(url, params={"symbols": json.dumps(symbols)})
            data = response.json()

            result: dict[str, float | None] = {s: None for s in symbols}
            for item in data:
                if "symbol" in item and "price" in item:
                    result[item["symbol"]] = float(item["price"])
            return result
        except FetcherError as e:
            logger.warning(f"[binance] Failed to fetch symbols {symbols}: {e}")
            return {s: None for s in symbols}
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[binance] Failed to parse batch response: {e}")
            return {s: None for s in symbols}

    @property
    def supports_batch(self) -> bool:
        """Binance supports batch fetching multiple symbols in one request."""
        return True

    async def fetch_batch(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], float | None]:
        """Fetch prices for multiple pairs in a single API call.

        Uses fetch methods determined by supports_pair() at startup.

        :param pairs: List of (base, quote) tuples to fetch.
        :returns: Dict mapping (base, quote) to price or None.
        """
        results: dict[tuple[str, str], float | None] = {}

        if not pairs:
            return results

        # Build symbols list from pair_info
        symbols: set[str] = set()
        needs_usdt_conversion: set[tuple[str, str]] = set()

        for base, quote in pairs:
            info = self._pair_info.get((base.lower(), quote.lower()))
            if not info:
                results[(base, quote)] = None
                continue

            symbol, needs_conversion = info
            symbols.add(symbol)
            if needs_conversion:
                symbols.add("USDTUSD")
                needs_usdt_conversion.add((base, quote))

        if not symbols:
            return results

        # Single API call for all symbols
        price_map = await self._fetch_symbols(list(symbols))

        # Get USDT rate for conversion
        usdt_rate = price_map.get("USDTUSD")

        # Check depeg once
        if usdt_rate is not None and self._is_depeg(usdt_rate):
            logger.warning(
                f"[binance] USDT depeg detected: rate={usdt_rate:.4f}. "
                "Excluding all USD pairs from batch."
            )
            usdt_rate = None

        # Map results back to original pairs
        for base, quote in pairs:
            if (base, quote) in results:
                continue  # Already marked as None (unsupported)

            info = self._pair_info.get((base.lower(), quote.lower()))
            if not info:
                results[(base, quote)] = None
                continue

            symbol, _ = info
            price = price_map.get(symbol)

            if price is None:
                results[(base, quote)] = None
            elif (base, quote) in needs_usdt_conversion:
                if usdt_rate is None:
                    results[(base, quote)] = None
                else:
                    results[(base, quote)] = price * usdt_rate
            else:
                results[(base, quote)] = price

        return results
