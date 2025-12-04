"""PriceAggregator: Median aggregation with outlier detection and drift limiting.

Algorithm:
    1. Filter out None/zero prices
    2. Calculate initial median across all valid sources
    3. Exclude outliers (prices deviating > max_deviation_percent from initial median)
    4. Recalculate median from filtered set
    5. Optionally apply drift limit vs previous_price
    6. Return None if fewer than min_sources remain or drift too large

.. code-block:: python

    >>> aggregator = PriceAggregator(min_sources=2, max_deviation_percent=5.0)
    >>> prices = {"coinbase": 100.0, "kraken": 100.5, "rogue": 200.0}
    >>> result = aggregator.aggregate(prices)
    >>> result.success
    True
    >>> result.price
    100.25
    >>> result.metadata["dropped"]
    {'rogue': 200.0}
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median as _median
from typing import TypedDict


class AggregationError(TypedDict, total=False):
    """Error information when aggregation fails.

    :ivar error: Error type identifier.
    :ivar available: Number of valid sources available.
    :ivar dropped: Dict of sources dropped as outliers.
    :ivar drift_percent: Actual drift percentage vs previous price.
    :ivar previous_price: Previous round's price.
    :ivar candidate_price: Price that was rejected due to drift.
    """

    error: str
    available: int
    dropped: dict[str, float]
    drift_percent: float
    previous_price: float
    candidate_price: float


class AggregationMetadata(TypedDict, total=False):
    """Metadata about a successful aggregation.

    :ivar sources: List of sources used in final calculation.
    :ivar dropped: Dict of sources dropped as outliers.
    :ivar count: Number of sources used.
    :ivar initial_median: Median before outlier filtering.
    """

    sources: list[str]
    dropped: dict[str, float]
    count: int
    initial_median: float


@dataclass
class AggregationResult:
    """Result of price aggregation.

    :ivar price: Aggregated price, or None if aggregation failed.
    :ivar metadata: Additional information about the aggregation.
    """

    price: float | None
    metadata: AggregationMetadata | AggregationError

    @property
    def success(self) -> bool:
        """Check if aggregation was successful."""
        return self.price is not None

    @property
    def error(self) -> str | None:
        """Get error type if aggregation failed."""
        if self.price is None:
            return self.metadata.get("error")
        return None


class PriceAggregator:
    """Aggregates prices from multiple sources with outlier detection.

    The aggregation algorithm:
        1. Filters invalid prices (None, zero, negative)
        2. Calculates initial median across all valid sources
        3. Excludes outliers that deviate > max_deviation_percent from initial median
        4. Recalculates final median from filtered set
        5. Optionally rejects if drift from previous_price exceeds drift_limit_percent

    :ivar min_sources: Minimum sources required for valid aggregation.
    :ivar max_deviation_percent: Max allowed deviation from median.
    :ivar drift_limit_percent: Max allowed change vs previous price.

    .. code-block:: python

        >>> agg = PriceAggregator(min_sources=2, max_deviation_percent=5.0)
        >>> result = agg.aggregate({"a": 100.0, "b": 101.0, "c": 99.0})
        >>> result.price
        100.0
    """

    def __init__(
        self,
        min_sources: int = 2,
        max_deviation_percent: float = 5.0,
        drift_limit_percent: float | None = None,
    ) -> None:
        """Initialize the aggregator.

        :param min_sources: Minimum number of valid sources required for aggregation.
        :param max_deviation_percent: Maximum allowed deviation from median before
            a source is considered an outlier (default 5%).
        :param drift_limit_percent: Optional maximum allowed change vs previous price.
            If exceeded, aggregation fails. None disables the check.
        :raises ValueError: If parameters are invalid.
        """
        if min_sources < 1:
            raise ValueError("min_sources must be at least 1")
        if max_deviation_percent <= 0:
            raise ValueError("max_deviation_percent must be positive")
        if drift_limit_percent is not None and drift_limit_percent <= 0:
            raise ValueError("drift_limit_percent must be positive if specified")

        self.min_sources = min_sources
        self.max_deviation_percent = max_deviation_percent
        self.drift_limit_percent = drift_limit_percent

    def aggregate(
        self,
        prices: dict[str, float | None],
        *,
        previous_price: float | None = None,
    ) -> AggregationResult:
        """Aggregate prices from multiple sources into a single median price.

        :param prices: Dict mapping source name to price (or None if fetch failed).
        :param previous_price: Optional previous round's price for drift checking.
            If None, drift check is skipped (useful for first round).
        :returns: AggregationResult with price and metadata, or None price with error info.

        .. code-block:: python

            >>> agg = PriceAggregator(min_sources=2)
            >>> result = agg.aggregate({"a": 100.0, "b": 101.0})
            >>> result.success
            True
            >>> result.price
            100.5
        """
        # Step 1: Filter out invalid prices
        valid: dict[str, float] = {
            k: v for k, v in prices.items() if v is not None and v > 0
        }

        if len(valid) < self.min_sources:
            return AggregationResult(
                price=None,
                metadata={
                    "error": "insufficient_sources",
                    "available": len(valid),
                },
            )

        # Step 2: Calculate initial median
        initial_median = _median(valid.values())

        # Step 3: Filter outliers
        filtered: dict[str, float] = {}
        dropped: dict[str, float] = {}

        for source, price in valid.items():
            deviation = abs(price - initial_median) / initial_median * 100
            if deviation <= self.max_deviation_percent:
                filtered[source] = price
            else:
                dropped[source] = price

        if len(filtered) < self.min_sources:
            return AggregationResult(
                price=None,
                metadata={
                    "error": "too_many_outliers",
                    "dropped": dropped,
                },
            )

        # Step 4: Calculate final median from filtered set
        final_median = _median(filtered.values())

        # Step 5: Apply drift limit if configured and previous price available
        if previous_price is not None and self.drift_limit_percent is not None:
            drift = abs(final_median - previous_price) / previous_price * 100
            if drift > self.drift_limit_percent:
                return AggregationResult(
                    price=None,
                    metadata={
                        "error": "drift_too_large",
                        "drift_percent": drift,
                        "previous_price": previous_price,
                        "candidate_price": final_median,
                    },
                )

        return AggregationResult(
            price=final_median,
            metadata={
                "sources": list(filtered.keys()),
                "dropped": dropped,
                "count": len(filtered),
                "initial_median": initial_median,
            },
        )
