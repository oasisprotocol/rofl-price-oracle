# Oasis Price Oracle

## About

A simple python-based client that runs in ROFL that queries a centralized 
exchange and stores price quotes to the Sapphire smart contract. Multiple
exchanges and trading pairs are supported.

## Contracts Maintained by Oasis

Feel free to use the [`PriceFeedDirectory`] singleton on Sapphire to 
discover public price feeds and register your own feeds:

| Contract             | Sapphire Mainnet                             | Sapphire Testnet                             |
|----------------------|----------------------------------------------|----------------------------------------------|
| `PriceFeedDirectory` | `0x1e1A7E15dd6eEeD48e00530d31fCf408F40E0A12` | `0xB3E8721A5E9bb84Cfa99b50131Ac47341B4a9EfF` |

Oasis maintains the following [`AggregatorV3Interface`] trading pair price 
feeds on Sapphire which you can use to build your DeFi dapp:

| Trading pair              | Sapphire Mainnet                             | Sapphire Testnet                             |
|---------------------------|----------------------------------------------|----------------------------------------------|
| `binance.us/rose/usdt`    | `0x9063375dc7A8f125d31DA43b8a02B1e065bAa081` | `0x47EFD60558012A64649c709b350f20C7a5f5e2Aa` |
| `binance.com/rose/usdc`   | `0xB14E3b717f9ddff678403ed7fF26614D23FBd99a` | `0x666938f7FBC353227F98DA43C050C8252eBfC0f7` |
| `binance.us/usdt/usd`     | `0xc8E6dEed5876Ee577252ecB70DA95286a5107D78` | TBA                                          |
| `binance.com/usdc/usd`    | `0xAC850546C3FFCA66A7D258eF14DF71135B55B44F` | TBA                                          |
| `binance.us/eth/usdt`     | TBA                                          | `0xcE4c39fAe52C0a723c275Ab0949F84d783aF7A38` |
| `binance.com/eth/usdc`    | TBA                                          | `0x01a6F876411B35102B7f30D801162dDE9b7593e6` |
| `bitstamp.net/usdc/usd`   | TBA                                          | `0x9F9929a1A6510Ff289C4e0B1357b6dfF9fC1BB20` |
| `bitstamp.net/usdt/usd`   | TBA                                          | `0xd29802275E41449f675A2650629fBB268D2Ab52d` |
| `bitstamp.net/usdc/usdt`  | TBA                                          | `0x1BeC39e4ca3B1Da500261333005578d8CA6A21b4` |

[`AggregatorV3Interface`]: https://docs.chain.link/chainlink-local/api-reference/v022/aggregator-v3-interface
[`PriceFeedDirectory`]: ./contracts/src/PriceFeedDirectory.sol

## Contracts

Solidity contracts for the price feed directory and a simple aggregator are 
located in the `contracts` folder. Move to that directory, then run:  

### Install dependencies

```shell
soldeer install
```

### Localnet

Localnet already has hardcoded accounts and ROFL app ids. To compile and deploy 
the price feed contract that keeps track of all aggregator contracts based 
on the app ID, exchange, and trading pair run:

```shell
forge create \
    --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
    --rpc-url http://localhost:8545 \
    --broadcast \
    PriceFeedDirectory
```

When running the oracle for the first time, it will deploy an appropriate 
aggregator contract and register it in the price feed directory.

Alternatively, you can compile and deploy a new aggregator contract directly by 
issuing:

```shell
forge create \
    --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
    --rpc-url http://localhost:8545 \
    --broadcast \
    SimpleAggregator \
    --constructor-args 000000000000000000000000000000000000000000 # your app ID in hex
```

### Testnet and Mainnet

Invoke commands above with:

```
--rpc-url https://testnet.sapphire.oasis.io
```

or

```
--rpc-url https://sapphire.oasis.io
```

### Running contract tests

1. Compile sapphire-foundry precompiles:

   ```shell
   pushd contracts/dependencies/@oasisprotocol-sapphire-foundry-0.1.2/precompiles
   cargo build --release
   popd
   ```

2. Now you can run the tests:

   ```shell
   cd contracts
   forge test
   ```

For more info see https://docs.oasis.io/build/tools/foundry

## Oasis price oracle

Python price oracle lives in the `oracle` folder.

1. Init python venv and install dependencies
   
   ```shell
   cd oracle
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Make sure you have your contracts compiled and ABIs ready in
   ../contracts/out/SimpleAggregator/PriceFeedDirectory.json
   and deployed.

3. For Localnet, the default price feed directory address will work and no 
   key management service is required. Simply run oracle:

   ```shell
   ./main.py
   ```

   For ROFL on Mainnet/Testnet where the key management service is available 
   at `/run/appd/appd.sock` Unix socket you can run:

   ```shell
   ./main.py --network sapphire-testnet
   ```
