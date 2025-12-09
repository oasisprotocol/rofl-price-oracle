"""Shared USDT/USD rate cache.

The oracle's main loop fetches usdt/usd as an aggregated pair and
stores the result here. The Binance fetcher reads from here to convert
USDT prices to USD.

This module exists because Binance only offers USDT pairs, not USD pairs.
By caching the USDT/USD rate from other sources (CoinGecko, Kraken, etc.),
Binance can provide accurate USD prices without making extra API calls.
"""

import logging
import time
from typing import ClassVar

logger = logging.getLogger(__name__)


class UsdtRateCache:
    """Thread-safe cache for USDT/USD exchange rate.

    Uses class variables for singleton-like behavior across all instances.
    The rate is updated by PriceOracle after each usdt/usd aggregation cycle.
    """

    _rate: ClassVar[float | None] = None
    _timestamp: ClassVar[float] = 0.0
    _ttl: ClassVar[float] = 300.0  # 5 minutes staleness threshold

    @classmethod
    def set(cls, rate: float) -> None:
        """Update the cached USDT/USD rate.

        :param rate: The new USDT/USD exchange rate.
        """
        cls._rate = rate
        cls._timestamp = time.time()
        logger.debug(f"USDT/USD rate updated: {rate:.6f}")

    @classmethod
    def get(cls) -> float | None:
        """Get the cached USDT/USD rate if fresh.

        :returns: The cached rate, or None if cache is empty or stale.
        """
        if cls._rate is None:
            return None
        if time.time() - cls._timestamp > cls._ttl:
            logger.debug("USDT/USD rate cache is stale")
            return None  # Stale
        return cls._rate

    @classmethod
    def is_stale(cls) -> bool:
        """Check if the cached rate is stale.

        :returns: True if cache is empty or older than TTL.
        """
        if cls._rate is None:
            return True
        return time.time() - cls._timestamp > cls._ttl

    @classmethod
    def get_age(cls) -> float | None:
        """Get the age of the cached rate in seconds.

        :returns: Age in seconds, or None if cache is empty.
        """
        if cls._timestamp == 0.0:
            return None
        return time.time() - cls._timestamp
