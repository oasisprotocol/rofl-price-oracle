"""AggregatedPair: Trading pair representation for aggregated price feeds.

Unlike the legacy Pair class which is tied to a specific exchange, AggregatedPair
uses a fixed "aggregated" provider prefix. The feed hash is computed as:
    keccak256(appIdHex + "/aggregated/" + base + "/" + quote)

This ensures consistent on-chain storage keys regardless of which API sources
are used to compute the aggregated price.

.. code-block:: python

    >>> pair = AggregatedPair("btc", "usd")
    >>> str(pair)
    'aggregated/btc/usd'
    >>> pair = AggregatedPair.from_string("eth/usd")
    >>> pair.pair_base
    'eth'
"""

from __future__ import annotations

from web3 import Web3


class AggregatedPair:
    """A trading pair that aggregates prices from multiple off-chain sources.

    :ivar pair_base: Base currency symbol (lowercase).
    :ivar pair_quote: Quote currency symbol (lowercase).
    """

    def __init__(self, pair_base: str, pair_quote: str) -> None:
        """Initialize an aggregated pair.

        :param pair_base: Base currency symbol (e.g., "btc", "eth", "rose").
        :param pair_quote: Quote currency symbol (e.g., "usd").
        """
        self.pair_base = pair_base.lower()
        self.pair_quote = pair_quote.lower()

    def __str__(self) -> str:
        """Return the pair identifier string for on-chain registration."""
        return f"aggregated/{self.pair_base}/{self.pair_quote}"

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"AggregatedPair({self.pair_base!r}, {self.pair_quote!r})"

    def __hash__(self) -> int:
        """Return hash for use in dicts and sets."""
        return hash(str(self))

    def __eq__(self, other: object) -> bool:
        """Check equality based on string representation."""
        if not isinstance(other, AggregatedPair):
            return NotImplemented
        return str(self) == str(other)

    def compute_feed_hash(self, app_id_bytes: bytes) -> bytes:
        """Compute the keccak256 hash used as the key in PriceFeedDirectory.

        The hash format matches the Solidity key scheme:
            keccak256(appIdHex/aggregated/base/quote)

        :param app_id_bytes: 21-byte ROFL app ID.
        :returns: 32-byte keccak256 hash matching the Solidity key format.

        .. code-block:: python

            >>> pair = AggregatedPair("btc", "usd")
            >>> app_id = bytes.fromhex("005a216eb7f450bcc1f534a7575fb33d611b463fa2")
            >>> hash_bytes = pair.compute_feed_hash(app_id)
            >>> len(hash_bytes)
            32
        """
        key_string = f"{app_id_bytes.hex()}/{self}"
        return Web3.keccak(text=key_string)

    @classmethod
    def from_string(cls, pair_str: str) -> AggregatedPair:
        """Parse a pair string in format "base/quote".

        :param pair_str: Pair string like "btc/usd" or "eth/usd".
        :returns: New AggregatedPair instance.
        :raises ValueError: If pair string format is invalid.

        .. code-block:: python

            >>> pair = AggregatedPair.from_string("rose/usd")
            >>> pair.pair_base
            'rose'
            >>> pair.pair_quote
            'usd'
        """
        parts = pair_str.lower().split("/")
        if len(parts) != 2:
            raise ValueError(
                f"Invalid pair format '{pair_str}'. Expected 'base/quote' (e.g., 'btc/usd')"
            )
        return cls(parts[0], parts[1])
