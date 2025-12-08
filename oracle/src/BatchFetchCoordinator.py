"""BatchFetchCoordinator: Centralized batch price fetching.

This module coordinates batch fetching from multiple price sources,
reducing API calls by leveraging batch-capable endpoints where available.

Architecture:
    - Groups all pairs by source
    - Calls fetch_batch() for batch-capable sources (single API call)
    - Falls back to individual fetch() for non-batch sources
    - Returns results organized by pair for distribution to observers
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .fetchers import BaseFetcher

logger = logging.getLogger(__name__)


class BatchFetchCoordinator:
    """Coordinates batch fetching from multiple price sources.

    Optimizes API usage by:
    - Batching multiple pairs into single requests where supported
    - Fetching from all sources concurrently
    - Tracking per-source failures for backoff integration

    :ivar fetchers: Dict mapping source names to fetcher instances.
    :ivar fetch_timeout: Timeout for fetch requests in seconds.
    """

    def __init__(
        self,
        fetchers: dict[str, BaseFetcher],
        fetch_timeout: float = 10.0,
    ) -> None:
        """Initialize the batch fetch coordinator.

        :param fetchers: Dict mapping source names to fetcher instances.
        :param fetch_timeout: Timeout for fetch requests (default: 10.0).
        """
        self.fetchers = fetchers
        self.fetch_timeout = fetch_timeout

    async def fetch_all(
        self,
        pairs: list[tuple[str, str]],
        active_sources: dict[str, list[str]] | None = None,
    ) -> dict[tuple[str, str], dict[str, float | None]]:
        """Fetch prices for all pairs from all sources.

        Uses batch fetching where available, concurrent individual fetches
        otherwise. Returns results organized by pair for easy distribution.

        :param pairs: List of (base, quote) tuples to fetch.
        :param active_sources: Optional dict mapping pair keys to list of
            active source names. If None, all sources are used for all pairs.
        :returns: Dict mapping (base, quote) to {source: price} dict.
        """
        if not pairs:
            return {}

        # Initialize results structure
        results: dict[tuple[str, str], dict[str, float | None]] = {
            pair: {} for pair in pairs
        }

        # Group pairs by source based on support
        source_pairs: dict[str, list[tuple[str, str]]] = {}
        for source, fetcher in self.fetchers.items():
            supported_pairs = [
                pair for pair in pairs
                if fetcher.supports_pair(pair[0], pair[1])
                and (
                    active_sources is None
                    or source in active_sources.get(f"{pair[0]}/{pair[1]}", [source])
                )
            ]
            if supported_pairs:
                source_pairs[source] = supported_pairs

        # Fetch from all sources concurrently
        tasks = [
            self._fetch_source_batch(source, pairs_list)
            for source, pairs_list in source_pairs.items()
        ]

        if not tasks:
            return results

        source_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge results into per-pair structure
        for (source, _), result in zip(
            source_pairs.items(), source_results, strict=True
        ):
            if isinstance(result, BaseException):
                logger.warning(f"[{source}] Batch fetch exception: {result}")
                # Mark all pairs for this source as failed
                for pair in source_pairs[source]:
                    results[pair][source] = None
            else:
                # result is dict[(base, quote), price]
                for pair, price in result.items():
                    if pair in results:
                        results[pair][source] = price

        return results

    async def _fetch_source_batch(
        self,
        source: str,
        pairs: list[tuple[str, str]],
    ) -> dict[tuple[str, str], float | None]:
        """Fetch all pairs from a single source.

        Uses batch fetching if supported, otherwise concurrent individual fetches.

        :param source: Source name.
        :param pairs: List of (base, quote) tuples to fetch.
        :returns: Dict mapping (base, quote) to price or None.
        """
        fetcher = self.fetchers.get(source)
        if not fetcher:
            return {pair: None for pair in pairs}

        try:
            if fetcher.supports_batch:
                # Use batch fetching - single API call
                logger.debug(f"[{source}] Batch fetching {len(pairs)} pairs")
                return await asyncio.wait_for(
                    fetcher.fetch_batch(pairs),
                    timeout=self.fetch_timeout,
                )
            else:
                # Fall back to concurrent individual fetches
                logger.debug(f"[{source}] Individual fetching {len(pairs)} pairs")
                tasks = [
                    self._fetch_single(fetcher, base, quote)
                    for base, quote in pairs
                ]
                prices = await asyncio.gather(*tasks)
                return dict(zip(pairs, prices, strict=True))

        except asyncio.TimeoutError:
            logger.warning(f"[{source}] Batch fetch timeout")
            return {pair: None for pair in pairs}
        except Exception as e:
            logger.warning(f"[{source}] Batch fetch error: {e}")
            return {pair: None for pair in pairs}

    async def _fetch_single(
        self,
        fetcher: BaseFetcher,
        base: str,
        quote: str,
    ) -> float | None:
        """Fetch a single pair with timeout.

        :param fetcher: Fetcher instance to use.
        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: Price or None on failure.
        """
        try:
            return await asyncio.wait_for(
                fetcher.fetch(base, quote),
                timeout=self.fetch_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"[{fetcher.name}] Timeout fetching {base}/{quote}")
            return None
        except Exception as e:
            logger.warning(f"[{fetcher.name}] Error fetching {base}/{quote}: {e}")
            return None
