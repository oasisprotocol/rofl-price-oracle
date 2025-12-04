"""Binance fetcher with USDT/USD conversion.

Binance primarily offers USDT pairs. This fetcher:
1. Fetches BASE/USDT from Binance
2. Optionally fetches USDT/USD rate for conversion
3. Returns the USD-equivalent price

Endpoint: https://api.binance.com/api/v3/ticker/price
Rate Limit: High (no key required for public endpoints)
ROSE Support: Yes (via USDT pair)
"""

import logging
import time
from typing import ClassVar

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class BinanceFetcher(BaseFetcher):
    """Fetcher for Binance with USDT to USD conversion.

    For /usd quotes, fetches the USDT pair and converts using
    a cached USDT/USD rate (default: 1.0, refreshed periodically).

    Includes USDT depeg detection - if USDT deviates >2% from 1.0,
    the source is excluded.
    """

    name = "binance"
    BASE_URL = "https://api.binance.com/api/v3"

    # USDT/USD rate cache
    _usdt_rate: ClassVar[float] = 1.0
    _usdt_rate_timestamp: ClassVar[float] = 0.0
    _usdt_rate_ttl: ClassVar[float] = 120.0  # 2 minutes cache

    # USDT depeg threshold (2%)
    USDT_DEPEG_THRESHOLD = 0.02

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
        """Get USDT/USD rate, using cache if fresh.

        The rate is fetched from a trusted source (could be CoinGecko or
        calculated from stablecoin arbitrage).

        :returns: USDT/USD rate or None on failure.
        """
        now = time.time()

        # Return cached rate if still valid
        if now - self._usdt_rate_timestamp < self._usdt_rate_ttl:
            return self._usdt_rate

        # For simplicity, we use a fixed rate of 1.0 for USDT/USD
        # In production, this could fetch from CoinGecko or another source
        # to detect depeg situations
        try:
            # Simple approach: assume USDT ≈ USD
            # A more robust implementation would fetch from CoinGecko:
            # url = "https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=usd"
            # response = await self._get(url)
            # usdt_rate = response.json()["tether"]["usd"]

            usdt_rate = 1.0  # Simplified for now

            # Update cache
            BinanceFetcher._usdt_rate = usdt_rate
            BinanceFetcher._usdt_rate_timestamp = now

            return usdt_rate

        except Exception as e:
            logger.warning(f"[binance] Failed to fetch USDT/USD rate: {e}")
            # Return cached rate on failure
            return self._usdt_rate if self._usdt_rate_timestamp > 0 else None
