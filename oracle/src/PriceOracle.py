import asyncio
import requests
import time
from web3 import Web3

from .ContractUtility import ContractUtility
from .RoflUtility import bech32_to_bytes
from .RoflUtilityAppd import RoflUtilityAppd
from .RoflUtilityLocalnet import RoflUtilityLocalnet


async def fetch_binance_com(pair_base: str, pair_quote: str) -> float:
    try:
        response = requests.get(f'https://api.binance.com/api/v3/ticker?symbol={pair_base.upper()}{pair_quote.upper()}')
        if response.status_code == 200:
            data = response.json()
            return float(data['lastPrice'])
        else:
            print(f"Error fetching price: HTTP {response.status_code}")
    except Exception as e:
        print(f"Error fetching Binance.com price: {e}")

async def fetch_binance_us(pair_base: str, pair_quote: str) -> float:
    try:
        response = requests.get(f'https://api.binance.us/api/v3/ticker?symbol={pair_base.upper()}{pair_quote.upper()}')
        if response.status_code == 200:
            data = response.json()
            return float(data['lastPrice'])
        else:
            print(f"Error fetching price: HTTP {response.status_code}")
    except Exception as e:
        print(f"Error fetching Binance.us price: {e}")

async def fetch_coinbase(pair_base: str, pair_quote: str) -> float:
    try:
        response = requests.get(f'https://api.exchange.coinbase.com/products/{pair_base.upper()}-{pair_quote.upper()}/ticker')
        if response.status_code == 200:
            data = response.json()
            if 'price' in data:
                return float(data['price'])
            else:
                print(f"Error fetching price: {data.get('error', 'Unknown error')}")
        else:
            print(f"Error fetching price: HTTP {response.status_code}")
    except Exception as e:
        print(f"Error fetching Coinbase price: {e}")

async def fetch_kraken(pair_base: str, pair_quote: str) -> float:
    try:
        response = requests.get(f'https://api.kraken.com/0/public/Ticker?pair={pair_base}{pair_quote}')
        if response.status_code == 200:
            data = response.json()
            if 'result' in data:
                # Kraken returns results with pair names as keys
                pair_data = list(data['result'].values())[0]
                price = pair_data['c'][0]  # 'c' is the last trade closed array

                # Store price with timestamp
                return float(price)
            else:
                print(f"Error fetching price: {data.get('error', 'Unknown error')}")
        else:
            print(f"Error fetching price: HTTP {response.status_code}")
    except Exception as e:
        print(f"Error fetching Kraken price: {e}")

async def fetch_bitstamp(pair_base: str, pair_quote: str) -> float:
    try:
        response = requests.get(f'https://www.bitstamp.net/api/v2/ticker/{pair_base.lower()}{pair_quote.lower()}/')
        if response.status_code == 200:
            data = response.json()
            if 'last' in data:
                # Bitstamp returns the last price directly
                price = data['last']

                # Store price with timestamp
                return float(price)
            else:
                print(f"Error fetching price: {data.get('error', 'Unknown error')}")
        else:
            print(f"Error fetching price: HTTP {response.status_code}")
    except Exception as e:
        print(f"Error fetching Bitstamp price: {e}")

EXCHANGE_FETCHERS = {
    'binance.com': fetch_binance_com,
    'binance.us': fetch_binance_us,
    'kraken.com': fetch_kraken,
    'coinbase.com': fetch_coinbase,
    'bitstamp.net': fetch_bitstamp,
}

# Predeployed price directory contract addresses based on the network.
DEFAULT_PRICE_FEED_ADDRESS = {
    "sapphire": None,
    "sapphire-testnet": "0xB3E8721A5E9bb84Cfa99b50131Ac47341B4a9EfF",
    "sapphire-localnet": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
}

# Number of decimals stored on-chain.
NUM_DECIMALS = 10

class Pair:
    def __init__(self, exchange: str, chain: str | None, pair_base: str, pair_quote: str):
        self.exchange = exchange
        self.chain = chain
        self.pair_base = pair_base
        self.pair_quote = pair_quote

    def __str__(self):
        if self.chain:
            return f"{self.exchange}/{self.chain}/{self.pair_base}/{self.pair_quote}"
        return f"{self.exchange}/{self.pair_base}/{self.pair_quote}"

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return str(self)==str(other)

    def compute_feed_hash(self, app_id_bytes: bytes):
        return Web3.keccak(text="/".join(
            (app_id_bytes.hex(), str(self))
        ))


class PriceOracle:
    def __init__(self,
                 address: str,
                 price_feed_address: str,
                 network_name: str,
                 exchanges_pairs: str,
                 api_keys: str,
                 fetch_period: int,
                 submit_period: int):
        contract_utility = ContractUtility(network_name)
        self.contract_abi, self.contract_bytecode = ContractUtility.get_contract('SimpleAggregator')
        self.contracts = {} # pair -> contract instance

        self.pairs = []
        for ep in exchanges_pairs.split(","):
            exchange: str
            pair_base: str
            pair_quote: str
            chain: str | None = None
            if ep.count("/") == 2:
                [exchange, pair_base, pair_quote] = ep.split("/")
            elif ep.count("/") == 3:
                [exchange, chain, pair_base, pair_quote] = ep.split("/")
            else:
                print(f"warning: invalid pair format '{ep}'. Ignoring.")
                continue

            if exchange not in EXCHANGE_FETCHERS:
                print(f"error: unsupported exchange {exchange}. Possible values are: {" ".join(EXCHANGE_FETCHERS.keys())}")
                exit(1)

            self.pairs.append(Pair(exchange, chain, pair_base, pair_quote))

        self.api_key = {}
        if api_keys is not None and len(api_keys) > 0:
            for api_key in api_keys.split(","):
                ak = api_key.split("=")
                self.api_key[ak[0]] = ak[1]

        self.fetch_period = fetch_period
        self.submit_period = submit_period
        if address is not None and len(address) > 0:
            for a in address.split(","):
                self.contracts[self.pairs[0]] = contract_utility.w3.eth.contract(address=a, abi=self.contract_abi, bytecode=self.contract_bytecode)

        price_feed_abi, _ = ContractUtility.get_contract('PriceFeedDirectory')
        self.price_feed_contract = contract_utility.w3.eth.contract(address=price_feed_address, abi=price_feed_abi)
        self.w3 = contract_utility.w3
        self.rofl_utility = RoflUtilityLocalnet(self.w3) if network_name == "sapphire-localnet" else RoflUtilityAppd()



    def detect_contract(self, pair: Pair, app_id_bytes: bytes):
        address = self.price_feed_contract.functions.feeds(
            pair.compute_feed_hash(app_id_bytes)
        ).call()

        if address == '0x0000000000000000000000000000000000000000':
            return

        contract = self.w3.eth.contract(address=address, abi=self.contract_abi, bytecode=self.contract_bytecode)
        self.contracts[pair] = contract
        print(f"Detected aggregator contract {self.contracts[pair].address} for {pair}")

        # Sanity check.
        print("decimals:", contract.functions.decimals().call())
        print("description:", contract.functions.description().call())
        if contract.functions.decimals().call() == 0:
            tx_params = contract.functions.setDecimals(NUM_DECIMALS).build_transaction({
                'gasPrice': self.w3.eth.gas_price,
            })
            result = self.rofl_utility.submit_tx(tx_params)
            print(f"Set decimals to {NUM_DECIMALS}. Result: {result}")

        if contract.functions.description().call() == "":
            tx_params = contract.functions.setDescription(str(pair)).build_transaction({
                'gasPrice': self.w3.eth.gas_price,
            })
            result = self.rofl_utility.submit_tx(tx_params)
            print(f"Set description to {str(pair)}. Result: {result}")


    def detect_or_deploy_contract(self, pair: Pair):
        # Fetch the current app ID
        app_id = self.rofl_utility.fetch_appid()
        app_id_bytes = bech32_to_bytes(app_id)

        if pair in self.contracts:
            return

        self.detect_contract(pair, app_id_bytes)
        if pair in self.contracts:
            return

        # Deploy the contract implicitly by calling add_feed().
        tx_params = self.price_feed_contract.functions.addFeed(
            "/".join((pair.exchange, pair.pair_base, pair.pair_quote)),
            "0x0000000000000000000000000000000000000000",
            False,
        ).build_transaction({
            'gasPrice': self.w3.eth.gas_price,
        })
        result = self.rofl_utility.submit_tx(tx_params)
        print(f"Contract deploy submitted. Result: {result}")

        self.detect_contract(pair, app_id_bytes)
        if pair in self.contracts:
            contract = self.contracts[pair]
            print(f"Detected aggregator contract {contract.address}")
        else:
            print(f"Aggregator contract not available. Aborting.")
            exit(2)


    async def observations_loop(self, pair:Pair):
        observations = []  # List of (uint256 price, uint64 timestamp) tuples for the current round
        last_submit = asyncio.get_event_loop().time()
        print(f"Starting price observation loop for {pair.pair_base}/{pair.pair_quote} on {pair.exchange}...")

        contract = self.contracts[pair]
        num_decimals = contract.functions.decimals().call()
        latest_round_data = contract.functions.latestRoundData().call()
        round_id = latest_round_data[0]

        # Price fetching loop
        while True:
            round_id+=1
            price = await EXCHANGE_FETCHERS[pair.exchange](pair.pair_base, pair.pair_quote)
            if price is None or price == 0:
                print(f"warning: {pair} price invalid: {price}. Ignoring.")
                await asyncio.sleep(self.fetch_period)
                continue

            print(f"{pair} price: ${price:.10f}")
            obs = (int(price * 10**num_decimals), int(asyncio.get_event_loop().time()))
            observations.append(obs)

            if asyncio.get_event_loop().time() - last_submit > self.submit_period:
                sorted_observations = sorted(observations)
                median_price = sorted_observations[int(len(observations)/2)][0]

                tx_params = contract.functions.submitObservation(
                    round_id,
                    median_price,
                    observations[0][1],
                    observations[-1][1],
                ).build_transaction({
                    'gasPrice': self.w3.eth.gas_price,
                })

                last_submit = asyncio.get_event_loop().time()
                result = self.rofl_utility.submit_tx(tx_params)
                print(f"Submitting observations. Result: {result}")
                observations = []

            await asyncio.sleep(self.fetch_period)

    async def run(self) -> None:
        tasks = []
        for pair in self.pairs:
            self.detect_or_deploy_contract(pair)
            tasks.append(
                asyncio.create_task(
                    self.observations_loop(pair)
                )
            )
            time.sleep(1)

        await asyncio.gather(*tasks)