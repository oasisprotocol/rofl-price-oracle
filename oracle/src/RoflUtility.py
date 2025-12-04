"""RoflUtility: Abstract base class for ROFL appd interaction."""

from abc import abstractmethod
from typing import Any

import bech32
from web3.types import TxParams


def bech32_to_bytes(app_id: str) -> bytes:
    """Decode a ROFL app ID from bech32 to raw bytes.

    :param app_id: Bech32-encoded app ID (e.g., "rofl1qr...").
    :returns: 21-byte raw app ID.
    :raises ValueError: If app_id is invalid bech32.
    """
    hrp, data = bech32.bech32_decode(app_id)
    if data is None:
        raise ValueError(f"Invalid bech32 app_id: {app_id}")

    # Convert 5-bit groups to bytes
    app_id_bytes = bech32.convertbits(data, 5, 8, False)
    if app_id_bytes is None:
        raise ValueError(f"Failed to convert app_id to bytes: {app_id}")

    return bytes(app_id_bytes)


class RoflUtility:
    """Abstract base class for ROFL utility implementations.

    Provides interface for app ID fetching, key management, and
    transaction submission via the ROFL appd daemon.
    """

    @abstractmethod
    def fetch_appid(self) -> str:
        """Fetch the current ROFL app ID.

        :returns: Bech32-encoded app ID.
        """
        pass

    @abstractmethod
    def fetch_key(self, id: str) -> str:
        """Fetch or generate a key by ID.

        :param id: Key identifier.
        :returns: Key value.
        """
        pass

    @abstractmethod
    def submit_tx(self, tx: TxParams) -> Any:
        """Submit a transaction via the ROFL appd.

        :param tx: Transaction parameters.
        :returns: Transaction result.
        """
        pass
