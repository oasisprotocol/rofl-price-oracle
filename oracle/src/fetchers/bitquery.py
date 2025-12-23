"""Bitquery fetcher.

Endpoint: https://graphql.bitquery.io (GraphQL)
Rate Limit: Points-based
ROSE Support: Yes (via DEX trades)
API Key: Required
"""

import logging

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class BitqueryFetcher(BaseFetcher):
    """Fetcher for Bitquery GraphQL API.

    Supports 40+ chains with DEX trade data.
    API key is REQUIRED.
    """

    name = "bitquery"
    BASE_URL = "https://graphql.bitquery.io"

    # GraphQL query for getting latest trade price
    PRICE_QUERY = """
    query ($base: String!, $quote: String!) {
        ethereum(network: ethereum) {
            dexTrades(
                baseCurrency: {is: $base}
                quoteCurrency: {is: $quote}
                options: {limit: 1, desc: "block.timestamp.unixtime"}
            ) {
                quotePrice
                block {
                    timestamp {
                        unixtime
                    }
                }
            }
        }
    }
    """

    # Map common symbols to contract addresses (for DEX queries)
    TOKEN_ADDRESSES = {
        "btc": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # WBTC on Ethereum
        "eth": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH on Ethereum
        "usdt": "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT on Ethereum
        "usdc": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC on Ethereum
    }

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from Bitquery via GraphQL.

        Note: This fetcher has higher latency than centralized exchange APIs
        due to GraphQL and DEX-based pricing.

        :param base: Base currency (e.g., "btc", "eth").
        :param quote: Quote currency (e.g., "usd", "usdt").
        :returns: Current price or None on failure.
        """
        if not self.api_key:
            logger.warning("[bitquery] API key required but not provided")
            return None

        # Get token addresses
        base_addr = self.TOKEN_ADDRESSES.get(base.lower())
        quote_addr = self.TOKEN_ADDRESSES.get(quote.lower())

        if not base_addr:
            logger.warning(f"[bitquery] Unknown base token: {base}")
            return None

        # For USD, we use USDT/USDC as proxy
        if quote.lower() == "usd":
            quote_addr = self.TOKEN_ADDRESSES.get("usdt")

        if not quote_addr:
            logger.warning(f"[bitquery] Unknown quote token: {quote}")
            return None

        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            response = await self._post(
                self.BASE_URL,
                json={
                    "query": self.PRICE_QUERY,
                    "variables": {"base": base_addr, "quote": quote_addr},
                },
                headers=headers,
            )
            data = response.json()

            # Navigate GraphQL response
            trades = (
                data.get("data", {})
                .get("ethereum", {})
                .get("dexTrades", [])
            )

            if not trades:
                logger.warning(f"[bitquery] No trades found for {base}/{quote}")
                return None

            price = trades[0].get("quotePrice")
            if price is None:
                logger.warning(f"[bitquery] No price in trade data: {trades[0]}")
                return None

            return float(price)

        except FetcherError as e:
            logger.warning(f"[bitquery] Failed to fetch {base}/{quote}: {e}")
            return None
        except (KeyError, ValueError, TypeError, IndexError) as e:
            logger.warning(f"[bitquery] Failed to parse response: {e}")
            return None

    async def supports_pair(self, base: str, quote: str) -> bool:
        """Check if pair is supported (must have token addresses).

        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: True if pair is supported.
        """
        base_supported = base.lower() in self.TOKEN_ADDRESSES
        quote_lower = quote.lower()
        quote_supported = quote_lower in self.TOKEN_ADDRESSES or quote_lower == "usd"
        return base_supported and quote_supported
