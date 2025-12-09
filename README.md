# Oasis ROFL Price Oracle

A ROFL-powered price oracle that aggregates cryptocurrency prices from multiple
off-chain sources and submits the median price to Sapphire smart contracts.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Off-Chain (ROFL)                          │
├──────────────────────────────────────────────────────────────┤
│  Coinbase ──┐                                                │
│  Kraken  ───┤                                                │
│  Bitstamp ──┼──► PriceAggregator ──► median ──► Observation │
│  CoinGecko ─┤     (outlier detection)            Buffer     │
│  CMC ───────┘                                       │        │
│                                                     ▼        │
│                              Every submit_period: Submit     │
└──────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────┐
│                    On-Chain (Sapphire)                       │
├──────────────────────────────────────────────────────────────┤
│  PriceFeedDirectory                                          │
│    └── feeds[keccak256("appId/aggregated/btc/usd")]          │
│            └── SimpleAggregator (btc/usd)                    │
│    └── feeds[keccak256("appId/aggregated/eth/usd")]          │
│            └── SimpleAggregator (eth/usd)                    │
└──────────────────────────────────────────────────────────────┘
```

### Key Features

- **Multi-source aggregation**: Queries multiple APIs (Coinbase, Kraken, CoinGecko, etc.)
- **Median with outlier detection**: Filters sources deviating >5% from median
- **Drift limiting**: Rejects sudden large price changes (configurable)
- **Exponential backoff**: Failed sources are temporarily excluded
- **ROSE/USD support**: Native support via Coinbase, CoinGecko, CoinMarketCap

## Quick Start

### Prerequisites

- Python 3.11+
- Foundry (for contract deployment)
- Access to Oasis Sapphire network

### Installation

```bash
# Clone and enter project root
cd rofl-price-oracle

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install the oracle package and runtime dependencies (from pyproject.toml)
pip install .

# (Optional) Install development extras (tests, linters)
pip install .[dev]
```

Or, using the root-level `Makefile`:

```bash
make install   # installs .[dev] using pyproject.toml
```

### Running the Oracle

The oracle is always started via Docker Compose and configured through environment variables.

#### Local Testing (without ROFL TEE)

Use `compose.local.yaml` for local development against `sapphire-localnet`:

```bash
# 1. Start sapphire-localnet (if not already running)
docker run -d -p8545:8545 -p8546:8546 ghcr.io/oasisprotocol/sapphire-localnet -test-mnemonic

# 2. Deploy mock contracts
cd contracts && forge script script/DeployMocks.s.sol --rpc-url sapphire-localnet --broadcast && cd ..

# 3. Configure environment
cp .env.example .env
# Edit .env with your configuration (PAIRS, SOURCES, PRICE_FEED_ADDRESS, etc.)

# 4. Run with local compose file
docker compose -f compose.local.yaml up --build
```

The `compose.local.yaml` uses `RoflUtilityLocalnet` with a hardcoded test key—no ROFL appd socket required.

#### Production Deployment (ROFL)

Use `compose.yaml` for ROFL TEE deployment. The compose file is referenced within the ROFL app manifest.

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env:
#   - NETWORK=sapphire-testnet or NETWORK=sapphire
#   - PRICE_FEED_ADDRESS=<your deployed PriceFeedDirectory>
#   - API keys for paid sources (if any)

# 2. Build, update, and deploy the ROFL app
oasis rofl build
oasis rofl update
oasis rofl deploy
```

The `compose.yaml` mounts `/run/rofl-appd.sock` for TEE-authenticated transactions via the ROFL runtime.

### Configuration

All configuration is done via environment variables in your `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `PAIRS` | `btc/usd` | Comma-separated trading pairs |
| `SOURCES` | `coinbase,kraken,bitstamp,coingecko` | Price sources to query |
| `MIN_SOURCES` | `2` | Minimum valid sources required |
| `MAX_DEVIATION_PERCENT` | `5.0` | Outlier threshold (%) |
| `DRIFT_LIMIT_PERCENT` | `10.0` | Max price change per round (0 to disable) |
| `FETCH_PERIOD` | `60` | Seconds between price fetches |
| `SUBMIT_PERIOD` | `300` | Seconds between on-chain submissions |
| `NETWORK` | `sapphire-localnet` | Target network |
| `PRICE_FEED_ADDRESS` | — | PriceFeedDirectory contract address |

See `.env.example` for full documentation including API key configuration.

### Available Price Sources

| Source | API Key | USD Pairs | ROSE Support |
|--------|---------|-----------|--------------|
| `coinbase` | No | Native | ✅ Yes |
| `kraken` | No | Native | ❌ No |
| `bitstamp` | No | Native | ❌ No |
| `coingecko` | Optional | All | ✅ Yes |
| `coinmarketcap` | Required | All | ✅ Yes |
| `coinapi` | Required | All | ✅ Yes |
| `eodhd` | Required | USD only | ✅ Yes |
| `binance` | No | USDT→USD | ✅ Yes |

## Contracts

Solidity contracts are in the `contracts` folder.

### Install Dependencies

```bash
cd contracts
soldeer install
```

### Deploy to Localnet

```bash
forge create \
    --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
    --rpc-url http://localhost:8545 \
    --broadcast \
    PriceFeedDirectory
```

The oracle will automatically deploy `SimpleAggregator` contracts for each
trading pair and register them in the `PriceFeedDirectory`.

### Deploy to Testnet/Mainnet

```bash
# Testnet
forge create ... --rpc-url https://testnet.sapphire.oasis.io

# Mainnet
forge create ... --rpc-url https://sapphire.oasis.io
```

### Mock Contracts (for Local Testing)

Mock contracts are provided for local development without TEE verification:

- `MockPriceFeedDirectory` - No ROFL app ID verification
- `MockSimpleAggregator` - No TEE check on `submitObservation()`

See [Local Testing](#local-testing-without-rofl-tee) in the Running section above for full setup instructions.

### Running Contract Tests

1. Build Sapphire precompiles:

   ```bash
   pushd contracts/dependencies/@oasisprotocol-sapphire-foundry-0.1.2/precompiles
   cargo build --release
   popd
   ```

2. Run tests:

   ```bash
   cd contracts
   forge test
   ```

## Project Structure

```
Makefile                     # Root Make targets (install, test, lint, run)
pyproject.toml               # Project metadata, dependencies, Ruff config

oracle/
├── main.py                  # CLI entry point
├── src/
│   ├── AggregatedPair.py    # Trading pair representation
│   ├── PriceAggregator.py   # Median aggregation with outlier detection
│   ├── SourceManager.py     # Per-source failure tracking & backoff
│   ├── PriceOracle.py       # Main orchestrator
│   ├── ContractUtility.py   # Contract ABI loading
│   ├── RoflUtility*.py      # ROFL appd integration
│   └── fetchers/            # Price source implementations
│       ├── base.py          # Abstract fetcher interface
│       ├── coinbase.py
│       ├── kraken.py
│       ├── bitstamp.py
│       ├── coingecko.py
│       ├── coinmarketcap.py
│       ├── coinapi.py
│       ├── eodhd.py
│       ├── bitquery.py
│       └── binance.py
└── tests/                   # Unit tests

contracts/
├── src/
│   ├── PriceFeedDirectory.sol   # Feed registry
│   ├── SimpleAggregator.sol     # Per-pair aggregator
│   ├── RoflAggregatorV3Interface.sol
│   └── mocks/                   # Mock contracts for local testing
│       ├── MockPriceFeedDirectory.sol
│       └── MockSimpleAggregator.sol
├── script/
│   └── DeployMocks.s.sol        # Foundry deployment script
└── test/
```

## Development (Linting & Tests)

From the project root:

```bash
# Install dependencies (runtime + dev)
make install

# Run unit tests
make test        # equivalent to: python -m pytest oracle/tests

# Lint with Ruff
make lint        # equivalent to: python -m ruff check oracle/src oracle/tests

# Run both lint and tests
make check
```

## Aggregation Algorithm

1. **Fetch**: Query all active sources concurrently
2. **Filter**: Remove None/zero/negative prices
3. **Initial Median**: Calculate median of valid prices
4. **Outlier Detection**: Exclude sources >5% from initial median
5. **Final Median**: Recalculate from filtered set
6. **Drift Check**: Reject if >10% change from previous round
7. **Accumulate**: Store observation with timestamp
8. **Submit**: Every `submit_period`, take median of observations and submit on-chain

## Rate Limit Considerations

- **CoinGecko free**: 30 calls/min → Safe with `FETCH_PERIOD=60`
- **CoinMarketCap free**: 333 calls/day → Use `SUBMIT_PERIOD≥300` (5 min)
- **Coinbase/Kraken/Bitstamp**: High limits, no key required

## License

MIT
