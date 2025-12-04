"""CoinGecko fetcher.

Endpoint: https://api.coingecko.com/api/v3/simple/price?ids={id}&vs_currencies={quote}
Rate Limit: 30 calls/min (free), higher with API key
ROSE Support: Yes (id: "oasis-network")
"""

import logging

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class CoinGeckoFetcher(BaseFetcher):
    """Fetcher for CoinGecko API.

    Supports all major cryptocurrencies including ROSE/USD.
    Free tier: 30 calls/min, 10k/month.
    Optional API key increases rate limit.
    """

    name = "coingecko"
    BASE_URL = "https://api.coingecko.com/api/v3"

    # Map common symbols to CoinGecko IDs
    COIN_IDS = {
        "btc": "bitcoin",
        "eth": "ethereum",
        "rose": "oasis-network",
        "usdt": "tether",
        "usdc": "usd-coin",
        "sol": "solana",
        "avax": "avalanche-2",
        "matic": "matic-network",
        "dot": "polkadot",
        "atom": "cosmos",
        "link": "chainlink",
        "uni": "uniswap",
        "aave": "aave",
    }

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from CoinGecko.

        :param base: Base currency (e.g., "btc", "eth", "rose").
        :param quote: Quote currency (e.g., "usd").
        :returns: Current price or None on failure.
        """
        coin_id = self.COIN_IDS.get(base.lower())
        if not coin_id:
            logger.warning(f"[coingecko] Unknown coin: {base}")
            return None

        quote_lower = quote.lower()
        url = f"{self.BASE_URL}/simple/price"

        headers = {}
        if self.api_key:
            headers["x-cg-pro-api-key"] = self.api_key

        try:
            response = await self._get(
                url,
                params={"ids": coin_id, "vs_currencies": quote_lower},
                headers=headers if headers else None,
            )
            data = response.json()

            if coin_id not in data:
                logger.warning(f"[coingecko] Coin {coin_id} not in response: {data}")
                return None

            if quote_lower not in data[coin_id]:
                logger.warning(
                    f"[coingecko] Quote {quote_lower} not available for {coin_id}"
                )
                return None

            return float(data[coin_id][quote_lower])

        except FetcherError as e:
            logger.warning(f"[coingecko] Failed to fetch {base}/{quote}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[coingecko] Failed to parse response: {e}")
            return None

    def supports_pair(self, base: str, quote: str) -> bool:
        """Check if pair is supported (base must be in COIN_IDS).

        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: True if pair is supported.
        """
        return base.lower() in self.COIN_IDS
