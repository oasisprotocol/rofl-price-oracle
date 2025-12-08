"""ContractUtility: Web3 initialization and contract ABI loading."""

import json
import os
from pathlib import Path

from eth_account import Account
from eth_account.signers.local import LocalAccount
from sapphirepy import sapphire
from web3 import Web3
from web3.middleware import SignAndSendRawMiddlewareBuilder


class ContractUtility:
    """Utility for Web3 connection and contract ABI loading.

    :ivar network: Network RPC URL.
    :ivar w3: Configured Web3 instance with Sapphire wrapping.
    """

    def __init__(self, network_name: str) -> None:
        """Initialize the contract utility.

        :param network_name: Name of the network to connect to.
        """
        networks = {
            "sapphire": "https://sapphire.oasis.io",
            "sapphire-testnet": "https://testnet.sapphire.oasis.io",
            "sapphire-localnet": "http://localhost:8545",
        }
        # RPC_URL env var overrides the default for the network
        self.network = os.environ.get("RPC_URL") or networks.get(network_name, network_name)

        self.w3 = Web3(Web3.HTTPProvider(self.network))
        if network_name == "sapphire-localnet":
            # Localnet uses a well-known test account for signing
            account: LocalAccount = Account.from_key(
                "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
            )
            self.w3.middleware_onion.add(SignAndSendRawMiddlewareBuilder.build(account))
            self.w3.eth.default_account = account.address
        self.w3 = sapphire.wrap(self.w3)

    @staticmethod
    def get_contract(contract_name: str) -> tuple[list, str]:
        """Fetch ABI and bytecode of a contract from the contracts folder.

        :param contract_name: Name of the contract (e.g., "SimpleAggregator").
        :returns: Tuple of (abi, bytecode).
        """
        output_path = (
            Path(__file__).parent.parent.parent
            / "contracts"
            / "out"
            / f"{contract_name}.sol"
            / f"{contract_name}.json"
        ).resolve()

        with open(output_path, "r") as file:
            contract_data = json.load(file)

        abi = contract_data["abi"]
        bytecode = contract_data["bytecode"]["object"]
        return abi, bytecode
