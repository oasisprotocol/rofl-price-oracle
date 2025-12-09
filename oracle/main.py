#!/usr/bin/env python3
"""ROFL Price Oracle.

Fetches cryptocurrency prices from multiple off-chain sources, computes
the median price and stores the results to on-chain aggregator contracts.

Start via Docker Compose with env vars. See README.md and .env.example for configuration.
"""

import argparse
import asyncio
import logging
import os
import sys

from .src.PriceOracle import DEFAULT_PRICE_FEED_ADDRESS, PriceOracle
from .src.fetchers import get_available_fetchers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_api_keys(api_key_str: str | None) -> dict[str, str]:
    """Parse comma-separated API key string into a dictionary.

    Format: source1=key1,source2=key2
    Example: coingecko=abc123,coinmarketcap=xyz789

    :param api_key_str: Comma-separated API key string.
    :returns: Dict mapping source names to API keys.
    """
    if not api_key_str:
        return {}

    api_keys = {}
    for item in api_key_str.split(","):
        item = item.strip()
        if "=" in item:
            source, key = item.split("=", 1)
            api_keys[source.strip().lower()] = key.strip()
    return api_keys


def parse_env_api_keys() -> dict[str, str]:
    """Parse API keys from individual environment variables.

    Looks for: API_KEY_COINGECKO, API_KEY_COINMARKETCAP, etc.

    :returns: Dict mapping source names to API keys.
    """
    api_keys = {}
    prefixes = ["API_KEY_", "APIKEY_"]

    for key, value in os.environ.items():
        for prefix in prefixes:
            if key.startswith(prefix) and value:
                source = key[len(prefix):].lower()
                api_keys[source] = value
                break

    return api_keys


def main() -> None:
    """Main entry point for the ROFL Price Oracle CLI."""
    available_sources = get_available_fetchers()

    parser = argparse.ArgumentParser(
        description="ROFL Price Oracle: Aggregated multi-source price feeds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available price sources:
  {', '.join(available_sources)}

Examples:
  # Basic usage with BTC/USD from multiple sources
  python -m oracle.main --pairs btc/usd --sources coinbase,kraken,coingecko

  # Multiple pairs with all free sources
  python -m oracle.main --pairs btc/usd,eth/usd,rose/usd \\
      --sources coinbase,kraken,bitstamp,coingecko

  # With API keys for premium sources
  python -m oracle.main --pairs btc/usd \\
      --sources coinbase,coingecko,coinmarketcap \\
      --api-keys coinmarketcap=your-api-key

Environment variables (CLI args take precedence):
  PAIRS, SOURCES, MIN_SOURCES, MAX_DEVIATION_PERCENT, DRIFT_LIMIT_PERCENT,
  FETCH_PERIOD, SUBMIT_PERIOD, NETWORK, PRICE_FEED_ADDRESS,
  API_KEY_COINGECKO, API_KEY_COINMARKETCAP, etc.
""",
    )

    parser.add_argument(
        "--pairs",
        type=str,
        help="Comma-separated trading pairs (e.g., btc/usd,eth/usd,rose/usd)",
        default=os.environ.get("PAIRS") or "btc/usd",
    )

    parser.add_argument(
        "--sources",
        type=str,
        help=f"Comma-separated price sources. Available: {', '.join(available_sources)}",
        default=os.environ.get("SOURCES") or "coinbase,kraken,bitstamp,coingecko",
    )

    parser.add_argument(
        "--min-sources",
        dest="min_sources",
        type=int,
        help="Minimum sources required for valid aggregation (default: 2)",
        default=int(os.environ.get("MIN_SOURCES") or "2"),
    )

    parser.add_argument(
        "--max-deviation",
        dest="max_deviation",
        type=float,
        help="Max price deviation percent before excluding outlier (default: 5.0)",
        default=float(os.environ.get("MAX_DEVIATION_PERCENT") or "5.0"),
    )

    parser.add_argument(
        "--drift-limit",
        dest="drift_limit",
        type=float,
        help="Max change vs previous price percent (default: 10.0, 0 to disable)",
        default=float(os.environ.get("DRIFT_LIMIT_PERCENT") or "10.0"),
    )

    parser.add_argument(
        "--network",
        type=str,
        help="Network to connect to (sapphire, sapphire-testnet, sapphire-localnet)",
        default=os.environ.get("NETWORK") or "sapphire-localnet",
    )

    parser.add_argument(
        "--fetch-period",
        dest="fetch_period",
        type=int,
        help="Seconds between fetching prices (minimum: 1, default: 60)",
        default=int(os.environ.get("FETCH_PERIOD") or "60"),
    )

    parser.add_argument(
        "--submit-period",
        dest="submit_period",
        type=int,
        help="Seconds between on-chain submissions (minimum: 6, default: 300)",
        default=int(os.environ.get("SUBMIT_PERIOD") or "300"),
    )

    parser.add_argument(
        "--price-feed-address",
        dest="price_feed_address",
        type=str,
        help="Address of PriceFeedDirectory contract",
        default=os.environ.get("PRICE_FEED_ADDRESS"),
    )

    parser.add_argument(
        "--address",
        type=str,
        help="Comma-separated aggregator contract addresses (optional, auto-detected if not provided)",
        default=os.environ.get("ADDRESS"),
    )

    parser.add_argument(
        "--api-keys",
        dest="api_keys",
        type=str,
        help="Comma-separated API keys (e.g., coingecko=abc,coinmarketcap=xyz)",
        default=os.environ.get("API_KEYS"),
    )

    parser.add_argument(
        "--fetch-timeout",
        dest="fetch_timeout",
        type=float,
        help="Timeout for individual fetch requests in seconds (default: 10.0)",
        default=float(os.environ.get("FETCH_TIMEOUT") or "10.0"),
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate arguments
    if args.fetch_period < 1:
        parser.error("--fetch-period must be at least 1 second")

    if args.submit_period < 6:
        parser.error("--submit-period must be at least 6 seconds")

    if args.min_sources < 1:
        parser.error("--min-sources must be at least 1")

    # Parse pairs and sources
    pairs = [p.strip() for p in args.pairs.split(",") if p.strip()]
    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]

    if not pairs:
        parser.error("At least one trading pair must be specified")

    if not sources:
        parser.error("At least one source must be specified")

    # Validate sources
    invalid_sources = [s for s in sources if s not in available_sources]
    if invalid_sources:
        parser.error(
            f"Unknown sources: {invalid_sources}. "
            f"Available: {', '.join(available_sources)}"
        )

    # Parse API keys (CLI + environment)
    api_keys = parse_env_api_keys()
    api_keys.update(parse_api_keys(args.api_keys))

    # Parse aggregator addresses
    aggregator_addresses = None
    if args.address:
        aggregator_addresses = [a.strip() for a in args.address.split(",")]

    # Get price feed address
    price_feed_address = args.price_feed_address
    if not price_feed_address:
        price_feed_address = DEFAULT_PRICE_FEED_ADDRESS.get(args.network)

    if not price_feed_address:
        parser.error(f"No price feed address configured for network {args.network}")

    # Handle drift limit (0 means disabled)
    drift_limit = args.drift_limit if args.drift_limit > 0 else None

    # Log configuration
    logger.info("=" * 60)
    logger.info("ROFL Price Oracle - Off-Chain Aggregation")
    logger.info("=" * 60)
    logger.info(f"Network:           {args.network}")
    logger.info(f"Price Feed:        {price_feed_address}")
    logger.info(f"Trading Pairs:     {', '.join(pairs)}")
    logger.info(f"Sources:           {', '.join(sources)}")
    logger.info(f"Min Sources:       {args.min_sources}")
    logger.info(f"Max Deviation:     {args.max_deviation}%")
    logger.info(f"Drift Limit:       {args.drift_limit}%" if drift_limit else "Drift Limit:       disabled")
    logger.info(f"Fetch Period:      {args.fetch_period}s")
    logger.info(f"Submit Period:     {args.submit_period}s")
    logger.info(f"Fetch Timeout:     {args.fetch_timeout}s")
    if api_keys:
        logger.info(f"API Keys:          {', '.join(api_keys.keys())}")
    logger.info("=" * 60)

    try:
        price_oracle = PriceOracle(
            network_name=args.network,
            pairs=pairs,
            sources=sources,
            price_feed_address=price_feed_address,
            aggregator_addresses=aggregator_addresses,
            api_keys=api_keys,
            fetch_period=args.fetch_period,
            submit_period=args.submit_period,
            min_sources=args.min_sources,
            max_deviation_percent=args.max_deviation,
            drift_limit_percent=drift_limit,
            fetch_timeout=args.fetch_timeout,
        )
        asyncio.run(price_oracle.run())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
