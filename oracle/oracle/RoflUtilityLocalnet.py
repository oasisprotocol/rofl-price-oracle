"""RoflUtilityLocalnet: ROFL utility for local development."""

import os
from typing import Any

import cbor2
from web3 import Web3
from web3.types import TxParams

from .RoflUtility import RoflUtility


class RoflUtilityLocalnet(RoflUtility):
    """ROFL utility implementation for localnet development.

    Uses direct Web3 transaction submission instead of appd.

    :ivar w3: Web3 instance for transaction submission.
    """

    def __init__(self, w3: Web3 | None = None) -> None:
        """Initialize the localnet utility.

        :param w3: Optional Web3 instance. Creates default if not provided.
        """
        self.w3 = w3
        if w3 is None:
            rpc_url = os.environ.get("RPC_URL", "http://localhost:8545")
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))

    def fetch_appid(self) -> str:
        """Return a dummy app ID for localnet.

        :returns: Fixed test app ID.
        """
        return "rofl11qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqtdv26p"

    def fetch_key(self, id: str) -> str:
        """Not implemented for localnet.

        :param id: Key identifier (unused).
        :returns: Raises NotImplementedError.
        """
        raise NotImplementedError("fetch_key is not supported on localnet")

    def submit_tx(self, tx: TxParams) -> Any:
        """Submit a transaction directly via Web3.

        :param tx: Transaction parameters.
        :returns: Dict with transaction result and receipt.
        """
        # Sign and send the transaction
        tx_hash = self.w3.eth.send_transaction(tx)

        # Wait for transaction receipt
        tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        # Check if transaction was successful
        if tx_receipt["status"] == 1:
            ok_cbor = cbor2.loads(bytes.fromhex("a1626f6b40"))
            return {"data": ok_cbor, "tx_receipt": tx_receipt}
        else:
            return {"tx_receipt": tx_receipt}
