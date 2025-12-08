"""CryptoCompare fetcher.

Endpoint: https://min-api.cryptocompare.com/data/price
Rate Limit: 100,000 calls/month (free tier)
USDT Support: Yes (fsym=USDT)
ROSE Support: Yes (fsym=ROSE)
"""

import logging

from .base import BaseFetcher, FetcherError, register_fetcher

logger = logging.getLogger(__name__)


@register_fetcher
class CryptoCompareFetcher(BaseFetcher):
    """Fetcher for CryptoCompare API.

    Provides simple price endpoint for cryptocurrency pairs.
    Uses the min-api endpoint which has generous free tier limits.
    """

    name = "cryptocompare"
    BASE_URL = "https://min-api.cryptocompare.com/data"

    async def fetch(self, base: str, quote: str) -> float | None:
        """Fetch price from CryptoCompare.

        :param base: Base currency (e.g., "btc", "eth", "usdt", "rose").
        :param quote: Quote currency (e.g., "usd").
        :returns: Current price or None on failure.
        """
        url = f"{self.BASE_URL}/price"
        params = {
            "fsym": base.upper(),
            "tsyms": quote.upper(),
        }

        # Add API key header if available
        headers = {}
        if self.api_key:
            headers["authorization"] = f"Apikey {self.api_key}"

        try:
            response = await self._get(
                url,
                params=params,
                headers=headers if headers else None,
            )
            data = response.json()

            # Check for error response
            if "Response" in data and data["Response"] == "Error":
                message = data.get("Message", "Unknown error")
                logger.warning(f"[cryptocompare] API error: {message}")
                return None

            price = data.get(quote.upper())
            if price is None:
                logger.warning(
                    f"[cryptocompare] No price for "
                    f"{base.upper()}/{quote.upper()}: {data}"
                )
                return None

            return float(price)

        except FetcherError as e:
            logger.warning(f"[cryptocompare] Failed to fetch {base}/{quote}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[cryptocompare] Failed to parse response: {e}")
            return None

    @property
    def supports_batch(self) -> bool:
        """CryptoCompare supports batch fetching with pricemulti endpoint."""
        return True

    async def fetch_batch(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], float | None]:
        """Fetch prices for multiple pairs in a single API call.

        CryptoCompare's /pricemulti endpoint accepts comma-separated fsyms
        and tsyms for efficient batch queries.

        :param pairs: List of (base, quote) tuples to fetch.
        :returns: Dict mapping (base, quote) to price or None.
        """
        results: dict[tuple[str, str], float | None] = {}

        if not pairs:
            return results

        # Collect unique bases and quotes
        bases: set[str] = set()
        quotes: set[str] = set()
        for base, quote in pairs:
            bases.add(base.upper())
            quotes.add(quote.upper())

        url = f"{self.BASE_URL}/pricemulti"
        params = {
            "fsyms": ",".join(bases),
            "tsyms": ",".join(quotes),
        }

        headers = {}
        if self.api_key:
            headers["authorization"] = f"Apikey {self.api_key}"

        try:
            response = await self._get(
                url,
                params=params,
                headers=headers if headers else None,
            )
            data = response.json()

            # Check for error response
            if "Response" in data and data["Response"] == "Error":
                message = data.get("Message", "Unknown error")
                logger.warning(f"[cryptocompare] Batch API error: {message}")
                for base, quote in pairs:
                    results[(base, quote)] = None
                return results

            # Map results back to original pairs
            # Response format: {"BTC": {"USD": 12345.67}, "ETH": {"USD": 456.78}}
            for base, quote in pairs:
                base_upper = base.upper()
                quote_upper = quote.upper()

                if base_upper not in data:
                    results[(base, quote)] = None
                    continue

                price = data[base_upper].get(quote_upper)
                if price is None:
                    results[(base, quote)] = None
                    continue

                results[(base, quote)] = float(price)

        except FetcherError as e:
            logger.warning(f"[cryptocompare] Batch fetch failed: {e}")
            for base, quote in pairs:
                results[(base, quote)] = None
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"[cryptocompare] Failed to parse batch response: {e}")
            for base, quote in pairs:
                results[(base, quote)] = None

        return results
