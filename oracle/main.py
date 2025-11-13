#!/usr/bin/env python3

from src.PriceOracle import DEFAULT_PRICE_FEED_ADDRESS, EXCHANGE_FETCHERS, PriceOracle
import argparse
import asyncio

def main():
    """
    Main method for the Python CLI tool.

    :return: None
    """
    parser = argparse.ArgumentParser(description="A Python CLI tool for compiling, deploying, and interacting with smart contracts.")

    parser.add_argument(
        "--address",
        type=str,
        help="Comma-separated address of the aggregator contract for the pairs to interact with. If none provided, the contract is looked up in the price feed directory. If it doesn't exist there, then a new aggregator contract is deployed and registered",
    )

    parser.add_argument(
        "--price-feed-address",
        dest="price_feed_address",
        type=str,
        help="Address of price feed directory contract",
    )

    parser.add_argument(
        "--network",
        help="Chain name to connect to "
             "(sapphire, sapphire-testnet, sapphire-localnet)",
        default="sapphire-localnet",
    )

    parser.add_argument(
        "--pair",
        help="Comma-separated exchange name + trading pair to observe. Example:\nbitstamp.net/btc/usd,uniswap.org/polygon/native/1bfd67037b42cf73acf2047067bd4f2c47d9bfd6",
        default="bitstamp.net/btc/usd",
        type=str,
    )

    parser.add_argument(
        "--fetch-period",
        dest="fetch_period",
        help="Amount of seconds between fetching token prices (minimum value 1)",
        default=10,
        type=int,
    )

    parser.add_argument(
        "--submit-period",
        dest="submit_period",
        help="Amount of seconds between submitting observations on-chain (minimum value 6)",
        default=60,
        type=int,
    )

    parser.add_argument(
        "--api-key",
        dest="api_key",
        help="Comma-separated API keys for exchanges. Example:\nbitstamp.net=AbCd123,binance.com=EfGh1234",
        type=str,
    )

    arguments = parser.parse_args()
    if arguments.fetch_period < 1:
        parser.error("--fetch-period must be at least 1 second")

    if arguments.submit_period < 6:
        parser.error("--submit-period must be at least 6 seconds")

    if arguments.price_feed_address is None or len(arguments.price_feed_address) == 0:
        arguments.price_feed_address = DEFAULT_PRICE_FEED_ADDRESS[arguments.network]

    print(f"Starting price oracle service. Using aggregator contract(s) {arguments.address} and price feed directory {arguments.price_feed_address} on {arguments.network}. Pair(s): {arguments.pair}. Fetch period: {arguments.fetch_period}s, Submit period: {arguments.submit_period}s.")

    price_oracle = PriceOracle(
        arguments.address,
        arguments.price_feed_address,
        arguments.network,
        arguments.pair,
        arguments.api_key,
        int(arguments.fetch_period), int(arguments.submit_period),
    )
    asyncio.run(price_oracle.run())

if __name__ == '__main__':
    main()
