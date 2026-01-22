"""
ROFL Price Oracle - Off-Chain Aggregation Module

This module provides price aggregation from multiple off-chain sources:
- AggregatedPair: Trading pair representation for aggregated feeds
- PriceAggregator: Median calculation with outlier detection
- SourceManager: Per-source failure tracking with exponential backoff
- PriceOracle: Main orchestrator for observation loops
- fetchers: Modular price fetcher implementations
"""

from .AggregatedPair import AggregatedPair
from .PriceAggregator import AggregationResult, PriceAggregator
from .PriceOracle import DEFAULT_PRICE_FEED_ADDRESS, NUM_DECIMALS, PriceOracle
from .SourceManager import SourceManager, SourceStatus

__all__ = [
    "AggregatedPair",
    "AggregationResult",
    "DEFAULT_PRICE_FEED_ADDRESS",
    "NUM_DECIMALS",
    "PriceAggregator",
    "PriceOracle",
    "SourceManager",
    "SourceStatus",
]
