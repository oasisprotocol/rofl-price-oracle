"""
Price fetchers for multiple API sources.

This module provides a unified interface for fetching cryptocurrency prices
from various exchanges and aggregator APIs.

Usage:
    from oracle.src.fetchers import get_fetcher, get_available_fetchers

    # Get list of available fetchers
    available = get_available_fetchers()
    # ['binance', 'bitstamp', 'bitquery', 'coinapi', 'coinbase', 'coingecko', 'coinmarketcap', 'eodhd', 'kraken']

    # Create a fetcher instance
    fetcher = get_fetcher("coinbase")
    price = await fetcher.fetch("btc", "usd")

    # For fetchers requiring API keys
    fetcher = get_fetcher("coinmarketcap", api_key="your-api-key")
"""

# Import base classes and utilities
from .base import (
    FETCHER_REGISTRY,
    BaseFetcher,
    FetcherConfigError,
    FetcherError,
    FetcherHTTPError,
    get_available_fetchers,
    get_fetcher,
    register_fetcher,
)

# Import all fetcher implementations to trigger registration
from .binance import BinanceFetcher
from .bitquery import BitqueryFetcher
from .bitstamp import BitstampFetcher
from .coinapi import CoinAPIFetcher
from .coinbase import CoinbaseFetcher
from .coingecko import CoinGeckoFetcher
from .coinmarketcap import CoinMarketCapFetcher
from .eodhd import EODHDFetcher
from .kraken import KrakenFetcher

__all__ = [
    # Base classes
    "BaseFetcher",
    "FetcherError",
    "FetcherConfigError",
    "FetcherHTTPError",
    # Registry functions
    "register_fetcher",
    "get_fetcher",
    "get_available_fetchers",
    "FETCHER_REGISTRY",
    # Fetcher implementations
    "BinanceFetcher",
    "BitstampFetcher",
    "BitqueryFetcher",
    "CoinAPIFetcher",
    "CoinbaseFetcher",
    "CoinGeckoFetcher",
    "CoinMarketCapFetcher",
    "EODHDFetcher",
    "KrakenFetcher",
]
