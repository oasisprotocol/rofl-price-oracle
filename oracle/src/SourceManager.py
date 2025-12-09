"""SourceManager: Per-source failure tracking with exponential backoff.

When a source fails (returns None, throws exception, or times out), it enters
a backoff period. The backoff duration doubles with each consecutive failure,
up to a maximum (default 5 minutes). A successful fetch resets the counter.

This prevents hammering failing APIs while allowing them to recover naturally.

.. code-block:: python

    >>> manager = SourceManager(["coinbase", "kraken", "coingecko"])
    >>> manager.get_active_sources()
    ['coinbase', 'kraken', 'coingecko']
    >>> manager.record_failure("kraken")
    5.0
    >>> manager.record_failure("kraken")
    10.0
    >>> manager.record_success("kraken")
    >>> manager.get_source_status("kraken").consecutive_failures
    0
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class SourceStatus:
    """Tracks the status of a single source.

    :ivar consecutive_failures: Number of consecutive failures.
    :ivar backoff_until: Unix timestamp when backoff period ends.
    :ivar total_failures: Total failures since tracking began.
    :ivar total_successes: Total successes since tracking began.
    """

    consecutive_failures: int = 0
    backoff_until: float = 0.0
    total_failures: int = 0
    total_successes: int = 0


class SourceManager:
    """Manages source health tracking with exponential backoff.

    Tracks per-source failures and applies exponential backoff:
        - First failure: 5 second backoff
        - Second failure: 10 second backoff
        - Third failure: 20 second backoff
        - ... up to max_backoff_seconds (default 300 = 5 minutes)

    :ivar sources: List of tracked source names.
    :ivar base_backoff_seconds: Initial backoff duration after first failure.
    :ivar max_backoff_seconds: Maximum backoff duration.

    .. code-block:: python

        >>> manager = SourceManager(["a", "b", "c"])
        >>> manager.record_failure("a")
        5.0
        >>> manager.is_source_active("a")
        False
    """

    DEFAULT_BASE_BACKOFF_SECONDS = 5
    DEFAULT_MAX_BACKOFF_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        sources: list[str],
        base_backoff_seconds: float = DEFAULT_BASE_BACKOFF_SECONDS,
        max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS,
    ) -> None:
        """Initialize the source manager.

        :param sources: List of source names to track.
        :param base_backoff_seconds: Initial backoff duration after first failure.
        :param max_backoff_seconds: Maximum backoff duration (caps exponential growth).
        """
        self.sources = list(sources)
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self._status: dict[str, SourceStatus] = {s: SourceStatus() for s in sources}

    def record_failure(self, source: str) -> float:
        """Record a failure for a source and apply exponential backoff.

        :param source: Source name that failed.
        :returns: The backoff duration in seconds.

        .. code-block:: python

            >>> manager = SourceManager(["api"])
            >>> manager.record_failure("api")
            5.0
            >>> manager.record_failure("api")
            10.0
        """
        if source not in self._status:
            self._status[source] = SourceStatus()

        status = self._status[source]
        status.consecutive_failures += 1
        status.total_failures += 1

        # Exponential backoff: base * 2^(failures-1), capped at max
        backoff_seconds = min(
            self.base_backoff_seconds * (2 ** (status.consecutive_failures - 1)),
            self.max_backoff_seconds,
        )
        status.backoff_until = time.time() + backoff_seconds

        return backoff_seconds

    def record_success(self, source: str) -> None:
        """Record a successful fetch, resetting the failure counter.

        :param source: Source name that succeeded.
        """
        if source not in self._status:
            self._status[source] = SourceStatus()

        status = self._status[source]
        status.consecutive_failures = 0
        status.backoff_until = 0.0
        status.total_successes += 1

    def get_active_sources(self) -> list[str]:
        """Get sources that are not currently in backoff.

        :returns: List of source names available for fetching.
        """
        now = time.time()
        return [s for s in self.sources if now >= self._status[s].backoff_until]

    def get_source_status(self, source: str) -> SourceStatus | None:
        """Get the status of a specific source.

        :param source: Source name to query.
        :returns: SourceStatus or None if source not tracked.
        """
        return self._status.get(source)

    def get_all_status(self) -> dict[str, SourceStatus]:
        """Get status of all sources.

        :returns: Dict mapping source names to their status.
        """
        return dict(self._status)

    def is_source_active(self, source: str) -> bool:
        """Check if a specific source is currently active (not in backoff).

        :param source: Source name to check.
        :returns: True if source is active, False if in backoff or unknown.
        """
        if source not in self._status:
            return False
        return time.time() >= self._status[source].backoff_until

    def get_backoff_remaining(self, source: str) -> float:
        """Get remaining backoff time for a source.

        :param source: Source name to check.
        :returns: Seconds remaining in backoff, or 0 if not in backoff.
        """
        if source not in self._status:
            return 0.0
        remaining = self._status[source].backoff_until - time.time()
        return max(0.0, remaining)

    def add_source(self, source: str) -> None:
        """Add a new source to track.

        :param source: Source name to add.
        """
        if source not in self.sources:
            self.sources.append(source)
        if source not in self._status:
            self._status[source] = SourceStatus()

    def remove_source(self, source: str) -> None:
        """Remove a source from tracking.

        :param source: Source name to remove.
        """
        if source in self.sources:
            self.sources.remove(source)
        self._status.pop(source, None)

    def reset_source(self, source: str) -> None:
        """Reset a source's status (clear backoff and failure count).

        :param source: Source name to reset.
        """
        if source in self._status:
            self._status[source] = SourceStatus()

    def reset_all(self) -> None:
        """Reset all sources to initial state."""
        self._status = {s: SourceStatus() for s in self.sources}
