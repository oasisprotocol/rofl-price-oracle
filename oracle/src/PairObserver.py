"""PairObserver: Per-pair price aggregation and on-chain submission.

This module handles the per-pair logic for:
- Receiving prices from multiple sources
- Aggregating via median with outlier detection
- Accumulating observations
- Submitting to on-chain aggregator contracts
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Callable

from .AggregatedPair import AggregatedPair
from .PriceAggregator import PriceAggregator
from .SourceManager import SourceManager
from .usdt_rate_cache import UsdtRateCache

if TYPE_CHECKING:
    from web3.contract import Contract

    from .fetchers import BaseFetcher
    from .RoflUtility import RoflUtility

logger = logging.getLogger(__name__)


class PairObserver:
    """Observer for a single trading pair.

    Handles price aggregation, observation accumulation, and on-chain submission
    for a specific trading pair.

    :ivar pair: The trading pair being observed.
    :ivar contract: On-chain aggregator contract instance.
    :ivar submit_period: Seconds between on-chain submissions.
    :ivar observations: Accumulated (price_scaled, timestamp) tuples.
    :ivar last_submit: Timestamp of last on-chain submission.
    """

    def __init__(
        self,
        pair: AggregatedPair,
        contract: Contract,
        rofl_utility: RoflUtility,
        sources: list[str],
        fetchers: dict[str, BaseFetcher],
        submit_period: int = 300,
        min_sources: int = 2,
        max_deviation_percent: float = 5.0,
        drift_limit_percent: float | None = 10.0,
        gas_price_fn: Callable[[], int] | None = None,
    ) -> None:
        """Initialize the pair observer.

        :param pair: Trading pair to observe.
        :param contract: On-chain aggregator contract.
        :param rofl_utility: ROFL utility for transaction submission.
        :param sources: List of source names that support this pair.
        :param fetchers: Dict mapping source names to fetcher instances.
        :param submit_period: Seconds between on-chain submissions (default: 300).
        :param min_sources: Minimum sources required for aggregation (default: 2).
        :param max_deviation_percent: Max deviation from median (default: 5.0).
        :param drift_limit_percent: Max change vs previous price (default: 10.0).
        :param gas_price_fn: Callable returning current gas price.
        """
        self.pair = pair
        self.contract = contract
        self.rofl_utility = rofl_utility
        self.sources = sources
        self.fetchers = fetchers
        self.submit_period = submit_period
        self.gas_price_fn = gas_price_fn

        # Initialize aggregator and source manager
        self.aggregator = PriceAggregator(
            min_sources=min_sources,
            max_deviation_percent=max_deviation_percent,
            drift_limit_percent=drift_limit_percent,
        )
        self.source_manager = SourceManager(sources)

        # State
        self.observations: list[tuple[int, int]] = []
        self.last_submit = time.time()
        self.last_good_median: float | None = None

        # Contract state
        self.decimals: int = contract.functions.decimals().call()
        latest_round_data = contract.functions.latestRoundData().call()
        self.round_id: int = latest_round_data[0]

        # Initialize last_good_median from chain if available
        if latest_round_data[1] > 0:
            self.last_good_median = float(latest_round_data[1]) / (10 ** self.decimals)
            logger.info(
                f"{pair}: Starting with on-chain price ${self.last_good_median:.6f}"
            )

        logger.info(
            f"PairObserver initialized for {pair} "
            f"(decimals={self.decimals}, round_id={self.round_id})"
        )

    def get_active_sources(self) -> list[str]:
        """Get list of sources not in backoff.

        :returns: List of active source names.
        """
        return self.source_manager.get_active_sources()

    def receive_prices(
        self, prices: dict[str, float | None]
    ) -> tuple[bool, float | None]:
        """Receive prices from sources and aggregate.

        Updates source manager with successes/failures and aggregates
        valid prices into an observation.

        :param prices: Dict mapping source name to price or None.
        :returns: Tuple of (success, aggregated_price).
        """
        # Update source manager
        valid_prices: dict[str, float | None] = {}
        for source, price in prices.items():
            if source not in self.sources:
                continue

            if price is None:
                backoff = self.source_manager.record_failure(source)
                logger.debug(
                    f"[{source}] No price for {self.pair}, backoff {backoff:.1f}s"
                )
            else:
                self.source_manager.record_success(source)
                valid_prices[source] = price

        # Aggregate prices
        agg_result = self.aggregator.aggregate(
            valid_prices, previous_price=self.last_good_median
        )

        if not agg_result.success:
            error_type = agg_result.error or "unknown"
            if valid_prices:
                price_strs = [
                    self._format_price(s, p) for s, p in valid_prices.items()
                ]
                logger.warning(
                    f"{self.pair}: Aggregation failed ({error_type}): "
                    f"prices=[{', '.join(price_strs)}], meta={agg_result.metadata}"
                )
            else:
                logger.warning(
                    f"{self.pair}: Aggregation failed ({error_type}): "
                    f"{agg_result.metadata}"
                )
            return False, None

        # Update state
        median_price = agg_result.price
        assert median_price is not None
        self.last_good_median = median_price
        meta = agg_result.metadata

        # Populate USDT rate cache if this is usdt/usd pair
        if self.pair.pair_base == "usdt" and self.pair.pair_quote == "usd":
            UsdtRateCache.set(median_price)

        # Log aggregated price
        sources_used = meta.get("sources", [])
        dropped_dict = meta.get("dropped", {})

        price_breakdown = [
            self._format_price(s, valid_prices[s])
            for s in sources_used
            if s in valid_prices
        ]
        dropped_strs = [self._format_price(s, p) for s, p in dropped_dict.items()]

        breakdown_str = ", ".join(price_breakdown)
        log_msg = f"{self.pair}: ${median_price:.6f} (median of [{breakdown_str}]"
        if dropped_strs:
            log_msg += f", dropped: [{', '.join(dropped_strs)}]"
        log_msg += ")"
        logger.info(log_msg)

        # Accumulate observation
        price_scaled = int(median_price * (10 ** self.decimals))
        timestamp = int(time.time())
        self.observations.append((price_scaled, timestamp))

        return True, median_price

    def should_submit(self) -> bool:
        """Check if it's time to submit observations on-chain.

        :returns: True if submit_period has elapsed since last submission.
        """
        return (
            len(self.observations) > 0
            and time.time() - self.last_submit > self.submit_period
        )

    def submit(self) -> bool:
        """Submit accumulated observations on-chain.

        Takes median of observations, submits to contract, and resets state.

        :returns: True if submission was successful.
        """
        if not self.observations:
            return False

        self.round_id += 1

        # Take median of accumulated observations
        sorted_obs = sorted(self.observations)
        final_price = sorted_obs[len(self.observations) // 2][0]

        # Build transaction
        gas_price = self.gas_price_fn() if self.gas_price_fn else 0
        tx_params = self.contract.functions.submitObservation(
            self.round_id,
            final_price,
            self.observations[0][1],  # startedAt
            self.observations[-1][1],  # updatedAt
        ).build_transaction({"gasPrice": gas_price})

        # Submit
        result = self.rofl_utility.submit_tx(tx_params)
        logger.info(
            f"{self.pair}: Round {self.round_id} submitted "
            f"(price=${final_price / 10**self.decimals:.6f}, "
            f"observations={len(self.observations)}). Result: {result}"
        )

        # Reset state
        self.last_submit = time.time()
        self.observations = []

        return True

    def _format_price(self, source: str, price: float) -> str:
        """Format price with API key indicator for logging.

        :param source: Source name.
        :param price: Price value.
        :returns: Formatted string like "coinbase[key]=$12345.67".
        """
        fetcher = self.fetchers.get(source)
        api_tag = "[key]" if fetcher and fetcher.has_api_key else ""
        return f"{source}{api_tag}=${price:.6f}"
