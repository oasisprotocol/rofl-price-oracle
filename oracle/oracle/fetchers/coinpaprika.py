"""Coinpaprika fetcher.

Endpoint: https://api.coinpaprika.com/v1/tickers/{coin_id}
Rate Limit: 20,000 calls/month (free tier)
USDT Support: Yes (id: usdt-tether)
ROSE Support: Yes (id: rose-oasis-network)
"""

import logging

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class CoinpaprikaFetcher(BaseFetcher):
    """Fetcher for Coinpaprika API.

    Provides ticker data for cryptocurrencies with price quotes
    in multiple fiat currencies. No API key required for basic usage.
    """

    name = "coinpaprika"
    BASE_URL = "https://api.coinpaprika.com/v1"

    # Map common symbols to Coinpaprika IDs
    # Format: {symbol}-{name}
    COIN_IDS = {
        "btc": "btc-bitcoin",
        "eth": "eth-ethereum",
        "usdt": "usdt-tether",
        "usdc": "usdc-usd-coin",
        "rose": "rose-oasis-network",
        "sol": "sol-solana",
        "avax": "avax-avalanche",
        "matic": "matic-polygon",
        "dot": "dot-polkadot",
        "atom": "atom-cosmos",
        "link": "link-chainlink",
        "uni": "uni-uniswap",
        "aave": "aave-aave",
    }

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from Coinpaprika.

        :param base: Base currency (e.g., "btc", "eth", "usdt").
        :param quote: Quote currency (e.g., "usd").
        :returns: Current price or None on failure.
        """
        coin_id = self.COIN_IDS.get(base.lower())
        if not coin_id:
            logger.warning(f"[coinpaprika] Unknown coin: {base}")
            return None

        url = f"{self.BASE_URL}/tickers/{coin_id}"

        try:
            response = await self._get(url)
            data = response.json()

            # Check for error response
            if "error" in data:
                logger.warning(
                    f"[coinpaprika] API error for {coin_id}: {data['error']}"
                )
                return None

            quotes = data.get("quotes", {})
            quote_data = quotes.get(quote.upper())

            if not quote_data:
                logger.warning(
                    f"[coinpaprika] Quote {quote.upper()} not available for {coin_id}"
                )
                return None

            price = quote_data.get("price")
            if price is None:
                logger.warning(f"[coinpaprika] No price in quote for {coin_id}")
                return None

            return float(price)

        except FetcherError as e:
            logger.warning(f"[coinpaprika] Failed to fetch {coin_id}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[coinpaprika] Failed to parse response for {coin_id}: {e}")
            return None

    async def supports_pair(self, base: str, quote: str) -> bool:
        """Check if pair is supported (base must be in COIN_IDS).

        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: True if pair is supported.
        """
        return base.lower() in self.COIN_IDS

    @property
    def supports_batch(self) -> bool:
        """Coinpaprika supports batch fetching via /tickers endpoint."""
        return True

    async def fetch_batch(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], float | None]:
        """Fetch prices for multiple pairs using the /tickers endpoint.

        Coinpaprika's /tickers endpoint returns all tickers at once,
        which can be filtered for efficiency with quotes parameter.

        :param pairs: List of (base, quote) tuples to fetch.
        :returns: Dict mapping (base, quote) to price or None.
        """
        results: dict[tuple[str, str], float | None] = {}

        if not pairs:
            return results

        # Filter to supported pairs
        supported_pairs: list[tuple[str, str]] = []
        coin_ids_needed: set[str] = set()
        quotes_needed: set[str] = set()

        for base, quote in pairs:
            coin_id = self.COIN_IDS.get(base.lower())
            if not coin_id:
                results[(base, quote)] = None
                continue

            supported_pairs.append((base, quote))
            coin_ids_needed.add(coin_id)
            quotes_needed.add(quote.upper())

        if not supported_pairs:
            return results

        # Use the /tickers endpoint with quotes filter
        # This returns all tickers but with only the requested quote currencies
        url = f"{self.BASE_URL}/tickers"
        params = {"quotes": ",".join(quotes_needed)}

        try:
            response = await self._get(url, params=params)
            data = response.json()

            # Check for error response
            if isinstance(data, dict) and "error" in data:
                logger.warning(f"[coinpaprika] Batch API error: {data['error']}")
                for base, quote in supported_pairs:
                    results[(base, quote)] = None
                return results

            # Build a lookup map from coin_id to ticker data
            ticker_map: dict[str, dict] = {}
            for ticker in data:
                ticker_id = ticker.get("id")
                if ticker_id:
                    ticker_map[ticker_id] = ticker

            # Map results back to original pairs
            for base, quote in supported_pairs:
                coin_id = self.COIN_IDS.get(base.lower())
                if not coin_id or coin_id not in ticker_map:
                    results[(base, quote)] = None
                    continue

                ticker = ticker_map[coin_id]
                quotes = ticker.get("quotes", {})
                quote_data = quotes.get(quote.upper())

                if not quote_data:
                    results[(base, quote)] = None
                    continue

                price = quote_data.get("price")
                if price is None:
                    results[(base, quote)] = None
                    continue

                results[(base, quote)] = float(price)

        except FetcherError as e:
            logger.warning(f"[coinpaprika] Batch fetch failed: {e}")
            for base, quote in supported_pairs:
                results[(base, quote)] = None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[coinpaprika] Failed to parse batch response: {e}")
            for base, quote in supported_pairs:
                results[(base, quote)] = None

        return results
