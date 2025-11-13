from eth_account import Account
from eth_account.signers.local import LocalAccount
import json
from pathlib import Path
from sapphirepy import sapphire
from web3 import Web3
from web3.middleware import SignAndSendRawMiddlewareBuilder

class ContractUtility:
    """
    Initializes the ContractUtility class.

    :param network_name: Name of the network to connect to
    :type network_name: str
    :return: None
    """

    def __init__(self, network_name: str):
        networks = {
            "sapphire": "https://sapphire.oasis.io",
            "sapphire-testnet": "https://testnet.sapphire.oasis.io",
            "sapphire-localnet": "http://localhost:8545",
        }
        self.network = networks[network_name] if network_name in networks else network_name

        self.w3 = Web3(Web3.HTTPProvider(self.network)) # TODO: Support async WebSocketProvider
        if network_name=="sapphire-localnet": # Testnet and Mainnet use w3 for queries only and Appd's sign-submit endpoint for everything else.
            account: LocalAccount = Account.from_key("0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
            self.w3.middleware_onion.add(SignAndSendRawMiddlewareBuilder.build(account))
            self.w3.eth.default_account = account.address
        self.w3 = sapphire.wrap(self.w3)

    def get_contract(contract_name: str) -> (str, str):
        """Fetches ABI of the given contract from the contracts folder"""
        output_path = (Path(__file__).parent.parent.parent / "contracts" / "out" / f"{contract_name}.sol" / f"{contract_name}.json").resolve()
        contract_data = ""
        with open(output_path, "r") as file:
            contract_data = json.load(file)

        abi, bytecode = contract_data["abi"], contract_data["bytecode"]["object"]
        return abi, bytecode
