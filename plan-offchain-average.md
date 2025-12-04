# Off-Chain Price Aggregation Implementation Plan

## Summary

Transform the ROFL Price Oracle from **per-exchange price feeds** to **off-chain aggregated price feeds**. One aggregator contract per trading pair (e.g., `btc/usd`) will store the median price calculated across multiple API sources. This is a v2 rewrite, so it is acceptable if the legacy per-exchange code path breaks.

---

## Current vs. Target Architecture

```
CURRENT:                                    TARGET:
┌─────────────┐                            ┌─────────────┐
│ Bitstamp    │──► Aggregator (bitstamp)   │ Coinbase    │─┐
├─────────────┤                            ├─────────────┤ │
│ Coinbase    │──► Aggregator (coinbase)   │ Kraken      │─┤
├─────────────┤                            ├─────────────┤ ├──► median ──► Aggregator (btc/usd)
│ Kraken      │──► Aggregator (kraken)     │ CoinGecko   │─┤
└─────────────┘                            ├─────────────┤ │
                                           │ Bitstamp    │─┘
                                           └─────────────┘
```

---

## Files to Modify

| File | Change |
|------|--------|
| `contracts/src/PriceFeedDirectory.sol` | Update comments for `aggregated/` prefix |
| `oracle/src/PriceOracle.py` | Complete rewrite: new AggregatedPair class, multi-source fetching, median aggregation |
| `oracle/main.py` | New CLI args: `--pairs`, `--sources`, `--min-sources` |
| `.env.example` | Updated configuration format |
| `oracle/src/fetchers/` (new) | Modular fetcher implementations per API |

---

## 1. Contract Changes (Minimal)

### PriceFeedDirectory.sol - Comment Updates Only

Update documentation to reflect the new aggregated key format and clarify that `providerChainPair` can be either aggregated or per-provider:

```solidity
// Key examples:
// - keccak256("005a216eb7f450bcc1f534a7575fb33d611b463fa2/aggregated/btc/usd")
// - keccak256("005a216eb7f450bcc1f534a7575fb33d611b463fa2/aggregated/rose/usd")
// Legacy per-exchange or DEX formats (still accepted):
// - keccak256("005a216eb7f450bcc1f534a7575fb33d611b463fa2/bitstamp.net/btc/usd")
// - keccak256("005a216eb7f450bcc1f534a7575fb33d611b463fa2/uniswap.org/polygon/native/1bfd67037b42cf73acf2047067bd4f2c47d9bfd6")
```

**No functional contract changes required** - the existing `addFeed()` accepts any string.

---

## 2. API Sources Reference

### Tier 1: Native USD Support (No API Key Required)

| API | Endpoint | Rate Limit | USD Pairs | ROSE Support |
|-----|----------|------------|-----------|--------------|
| **[Coinbase](https://www.coinbase.com/price/oasis-network)** | `api.exchange.coinbase.com/products/{BASE}-USD/ticker` | High | BTC, ETH, + 100s | **Yes** |
| **Kraken** | `api.kraken.com/0/public/Ticker?pair={BASE}USD` | High | BTC, ETH, + 50s | No (API returns `Unknown asset pair`) |
| **Bitstamp** | `bitstamp.net/api/v2/ticker/{base}usd/` | High | BTC, ETH, + 20s | No |

> **ROSE/USD Sources**: Coinbase (free) + CoinGecko (free) + CoinMarketCap (free tier w/ API key) = 3 sources. Meets MIN_SOURCES=2 with redundancy.

### Tier 2: Aggregator APIs (Free Tier Available)

| API | Endpoint | Free Tier | USD Pairs | ROSE Support |
|-----|----------|-----------|-----------|--------------|
| **[CoinGecko](https://www.coingecko.com/en/api)** | `/simple/price?ids={id}&vs_currencies=usd` | 30 calls/min, 10k/month | All | **Yes** (`oasis-network`) |
| **[CoinMarketCap](https://coinmarketcap.com/api/)** | `/v2/cryptocurrency/quotes/latest` | 333 calls/day | All | **Yes** |

### Tier 3: Professional APIs (API Key Required)

| API | Endpoint | Pricing | Features |
|-----|----------|---------|----------|
| **[CoinAPI](https://www.coinapi.io/)** | REST + WebSocket | $25 free credits, then $0.20-$5.26/1k calls | 400+ exchanges, 99.9% uptime SLA |
| **[EODHD](https://eodhd.com/financial-apis/fundamental-data-for-cryptocurrencies)** | `eodhd.com/api/real-time/{SYM}-USD.CC` | ~$19.99/mo for 100k calls/day | 2600+ USD pairs, WebSocket |
| **[Bitquery](https://bitquery.io/products/crypto-price-api)** | GraphQL + WebSocket + Kafka | Points-based | 40+ chains, Price Index with SMA/OHLCV |

### Tier 4: USDT-Based (Requires Conversion)

| API | Note |
|-----|------|
| **Binance.com** | USDT pairs only. Multiply by USDT/USD rate (~1.0) from CoinGecko |
| **Binance.us** | Some USD pairs available for US users |

---

## 3. Python Implementation

### 3.1 New Configuration Format

```env
# .env.example
PAIRS=btc/usd,eth/usd,rose/usd
SOURCES=coinbase,kraken,bitstamp,coingecko,coinmarketcap
MIN_SOURCES=2
MAX_DEVIATION_PERCENT=5.0
DRIFT_LIMIT_PERCENT=10.0  # Optional: max allowed change vs previous round

# API keys
API_KEY_COINGECKO=           # Optional, increases rate limit
API_KEY_COINMARKETCAP=       # Required for CoinMarketCap source
API_KEY_COINAPI=             # Optional, for CoinAPI source
API_KEY_EODHD=               # Optional, for EODHD source
API_KEY_BITQUERY=            # Optional, for Bitquery source

NETWORK=sapphire-testnet
FETCH_PERIOD=60              # Seconds between price fetches
SUBMIT_PERIOD=300            # Seconds between on-chain submissions (5 min default)
# NOTE: SUBMIT_PERIOD < 300 (5 min) requires CoinMarketCap paid API due to 333 calls/day free tier limit
```

Notes:
- `PAIRS` and `SOURCES` replace the old single `PAIR` configuration.
- CLI defaults should read from env vars first and then be overridable via flags.

### 3.2 New Directory Structure

```
oracle/src/
├── PriceOracle.py          # Main orchestrator (rewritten for aggregated feeds)
├── AggregatedPair.py       # New: Pair class for aggregated feeds
├── PriceAggregator.py      # New: Median + drift + outlier detection
├── SourceManager.py        # New: Per-source failure/backoff tracking
├── fetchers/               # New: Modular fetcher implementations
│   ├── __init__.py
│   ├── base.py             # Abstract fetcher interface + shared AsyncClient
│   ├── coinbase.py
│   ├── kraken.py
│   ├── bitstamp.py
│   ├── coingecko.py
│   ├── coinmarketcap.py
│   ├── coinapi.py
│   ├── eodhd.py
│   └── bitquery.py
├── ContractUtility.py      # Unchanged
├── RoflUtility.py          # Unchanged
├── RoflUtilityAppd.py      # Unchanged
└── RoflUtilityLocalnet.py  # Unchanged
```

### 3.3 Core Classes

#### AggregatedPair

```python
class AggregatedPair:
    def __init__(self, pair_base: str, pair_quote: str):
        self.pair_base = pair_base.lower()
        self.pair_quote = pair_quote.lower()

    def __str__(self):
        return f"aggregated/{self.pair_base}/{self.pair_quote}"

    def compute_feed_hash(self, app_id_bytes: bytes) -> bytes:
        return Web3.keccak(text=f"{app_id_bytes.hex()}/{self}")
```

#### PriceAggregator

```python
from statistics import median as _median

class PriceAggregator:
    def __init__(
        self,
        min_sources: int = 2,
        max_deviation_percent: float = 5.0,
        drift_limit_percent: float | None = None,
    ):
        self.min_sources = min_sources
        self.max_deviation_percent = max_deviation_percent
        self.drift_limit_percent = drift_limit_percent

    def aggregate(
        self,
        prices: dict[str, float],
        *,
        previous_price: float | None = None,
    ) -> tuple[float | None, dict]:
        """
        Returns (median_price, metadata) or (None, error_info)

        1. Filter out None/zero prices
        2. Calculate initial median across sources
        3. Exclude outliers (>max_deviation_percent from initial median)
        4. Recalculate median from filtered set
        5. Optionally apply drift limit vs previous_price
        6. Return None if fewer than min_sources remain or drift too large
        """
        valid = {k: v for k, v in prices.items() if v is not None and v > 0}

        if len(valid) < self.min_sources:
            return None, {'error': 'insufficient_sources', 'available': len(valid)}

        initial_median = _median(valid.values())

        filtered = {
            k: v
            for k, v in valid.items()
            if abs(v - initial_median) / initial_median * 100 <= self.max_deviation_percent
        }
        dropped = {k: v for k, v in valid.items() if k not in filtered}

        if len(filtered) < self.min_sources:
            return None, {'error': 'too_many_outliers', 'dropped': dropped}

        final_median = _median(filtered.values())

        if previous_price is not None and self.drift_limit_percent is not None:
            drift = abs(final_median - previous_price) / previous_price * 100
            if drift > self.drift_limit_percent:
                return None, {
                    'error': 'drift_too_large',
                    'drift_percent': drift,
                    'previous_price': previous_price,
                    'candidate_price': final_median,
                }

        return final_median, {
            'sources': list(filtered.keys()),
            'dropped': dropped,
            'count': len(filtered),
            'initial_median': initial_median,
        }
```

### 3.4 SourceManager (Backoff)

```python
class SourceManager:
    def __init__(self, sources: list[str]):
        self.sources = sources
        self.failures = {s: 0 for s in sources}
        self.backoff_until = {s: 0.0 for s in sources}

    def record_failure(self, source: str):
        self.failures[source] += 1
        # Exponential backoff with an upper bound (e.g., 5 minutes)
        backoff_seconds = min(5 * 2 ** (self.failures[source] - 1), 300)
        self.backoff_until[source] = time.time() + backoff_seconds

    def record_success(self, source: str):
        self.failures[source] = 0
        self.backoff_until[source] = 0.0

    def get_active_sources(self) -> list[str]:
        now = time.time()
        return [s for s in self.sources if now >= self.backoff_until[s]]
```

### 3.5 Observation Loop (Rewritten for Aggregation)

```python
async def aggregated_observations_loop(self, pair: AggregatedPair):
    observations = []
    last_submit = time.time()
    contract = self.contracts[pair]
    decimals = contract.functions.decimals().call()
    round_id = contract.functions.latestRoundData().call()[0]
    aggregator = PriceAggregator(
        self.min_sources,
        self.max_deviation,
        drift_limit_percent=self.drift_limit_percent,
    )
    source_manager = SourceManager(self.sources)
    last_good_median = None

    while True:
        # Fetch from all sources concurrently
        active_sources = source_manager.get_active_sources()
        if not active_sources:
            print(f"{pair}: no active sources, sleeping...")
            await asyncio.sleep(self.fetch_period)
            continue

        tasks = [
            self.fetch_with_timeout(source, pair.pair_base, pair.pair_quote)
            for source in active_sources
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        prices = {}
        for source, result in zip(active_sources, results):
            if isinstance(result, Exception):
                print(f"[{source}] Error: {result}")
                source_manager.record_failure(source)
            elif result is None:
                print(f"[{source}] returned no price")
                source_manager.record_failure(source)
            else:
                source_manager.record_success(source)
                prices[source] = result

        median, meta = aggregator.aggregate(prices, previous_price=last_good_median)
        if median is None:
            print(f"Aggregation failed: {meta}")
            # Keep last_good_median; do not submit a new round
            await asyncio.sleep(self.fetch_period)
            continue

        last_good_median = median
        print(f"{pair}: ${median:.6f} (from {meta['count']} sources: {meta['sources']}, dropped: {list(meta.get('dropped', {}).keys())})")
        observations.append((int(median * 10**decimals), int(time.time())))

        if time.time() - last_submit > self.submit_period:
            round_id += 1
            sorted_obs = sorted(observations)
            final_price = sorted_obs[len(observations) // 2][0]

            tx = contract.functions.submitObservation(
                round_id, final_price, observations[0][1], observations[-1][1]
            ).build_transaction({'gasPrice': self.w3.eth.gas_price})

            result = self.rofl_utility.submit_tx(tx)
            print(f"Round {round_id} submitted: {result}")

            last_submit = time.time()
            observations = []

        await asyncio.sleep(self.fetch_period)
```

---

## 4. Fetcher Implementations

### CoinGecko (Recommended for ROSE/USD)

```python
COINGECKO_IDS = {
    'btc': 'bitcoin',
    'eth': 'ethereum',
    'rose': 'oasis-network',
    'usdt': 'tether',
    'usdc': 'usd-coin',
}

async def fetch_coingecko(base: str, quote: str, api_key: str = None) -> float | None:
    coin_id = COINGECKO_IDS.get(base.lower())
    if not coin_id or quote.lower() != 'usd':
        return None

    headers = {'x-cg-pro-api-key': api_key} if api_key else {}
    url = f'https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd'

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()[coin_id]['usd']
    return None
```

Fetcher design notes:
- All fetchers should share a process-wide `httpx.AsyncClient` (or a small pool) configured with sensible limits and timeouts, rather than constructing a new client per request.
- Each fetcher returns `float | None` and logs HTTP/network errors; `SourceManager` handles backoff based on `None`/exceptions.
- For CoinGecko/CoinMarketCap/CoinAPI, we can later add batching (multiple pairs per call) once the basic per-pair implementation is stable.

**Rate limit considerations:**
- CoinGecko free tier: 30 calls/min. With 3 pairs × 1 call/min = 3 calls/min (safe margin).
- CoinMarketCap free tier: 333 calls/day. With SUBMIT_PERIOD=300 (5 min default):
  - 12 submissions/hour × 24 = 288 calls/day (within limit ✓)
  - For faster updates, use batching (`?symbol=BTC,ETH,ROSE`) or upgrade to paid API.
- If running multiple oracle instances, coordinate or partition pairs to avoid hitting rate limits.

### CoinMarketCap

```python
async def fetch_coinmarketcap(base: str, quote: str, api_key: str) -> float | None:
    if not api_key:
        return None

    url = 'https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest'
    headers = {'X-CMC_PRO_API_KEY': api_key}
    params = {'symbol': base.upper(), 'convert': quote.upper()}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()['data'][base.upper()][0]
            return data['quote'][quote.upper()]['price']
    return None
```

### CoinAPI

```python
async def fetch_coinapi(base: str, quote: str, api_key: str) -> float | None:
    if not api_key:
        return None

    url = f'https://rest.coinapi.io/v1/exchangerate/{base.upper()}/{quote.upper()}'
    headers = {'X-CoinAPI-Key': api_key}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()['rate']
    return None
```

### EODHD

```python
async def fetch_eodhd(base: str, quote: str, api_key: str) -> float | None:
    if not api_key or quote.lower() != 'usd':
        return None

    symbol = f'{base.upper()}-USD.CC'
    url = f'https://eodhd.com/api/real-time/{symbol}?api_token={api_key}&fmt=json'

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json().get('close')
    return None
```

### Bitquery (GraphQL)

```python
async def fetch_bitquery(base: str, quote: str, api_key: str) -> float | None:
    if not api_key:
        return None

    # Note: Bitquery uses GraphQL - this is simplified
    query = """
    query ($base: String!) {
        EVM {
            DEXTradeByTokens(where: {Trade: {Currency: {Symbol: {is: $base}}}}) {
                Trade {
                    PriceInUSD
                }
            }
        }
    }
    """
    url = 'https://graphql.bitquery.io'
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={'query': query, 'variables': {'base': base.upper()}},
                                  headers=headers, timeout=10)
        if resp.status_code == 200:
            # Parse GraphQL response for price
            data = resp.json()
            trades = data.get('data', {}).get('EVM', {}).get('DEXTradeByTokens', [])
            if trades:
                return trades[0]['Trade']['PriceInUSD']
    return None
```

### Binance (USDT Conversion)

For Binance.com (USDT-based pairs):

- Fetch `BASE/USDT` from Binance.
- Fetch `USDT/USD` from CoinGecko (or another stablecoin source).
- Multiply the two to obtain an implied `BASE/USD` price.

Implementation notes:
- Cache `USDT/USD` for a short TTL (e.g., 60–120 seconds) to minimize upstream calls.
- Track this in aggregation metadata so it is clear which prices depend indirectly on CoinGecko.

---

## 5. CLI Changes (main.py)

```python
parser.add_argument("--pairs",
    help="Comma-separated trading pairs: btc/usd,eth/usd,rose/usd",
    default=os.environ.get("PAIRS", "btc/usd"))

parser.add_argument("--sources",
    help="Comma-separated sources: coinbase,kraken,bitstamp,coingecko,coinmarketcap",
    default=os.environ.get("SOURCES", "coinbase,kraken,bitstamp,coingecko"))

parser.add_argument("--min-sources", dest="min_sources", type=int,
    help="Minimum sources required for valid aggregation",
    default=int(os.environ.get("MIN_SOURCES", "2")))

parser.add_argument("--max-deviation", dest="max_deviation", type=float,
    help="Max price deviation percent before excluding outlier",
    default=float(os.environ.get("MAX_DEVIATION_PERCENT", "5.0")))
```

Additional CLI/env behavior:
- Remove legacy `--pair` / `PAIR` usage and rely solely on `--pairs` / `PAIRS`.
- Make `--network`, `--fetch-period`, and `--submit-period` default from `NETWORK`, `FETCH_PERIOD`, and `SUBMIT_PERIOD` env vars respectively, with hardcoded fallbacks as a last resort.
- Validate `--sources` against the available fetchers at startup and exit with a clear error if an unknown source is configured.

---

## 6. Error Handling

### Source Failure Backoff

- Use `SourceManager` to track per-source failures and apply exponential backoff with an upper bound (e.g., 5 minutes).
- Exclude backed-off sources from the aggregation loop by using `get_active_sources()`.

### Aggregation Failure Handling

When aggregation fails (insufficient sources, too many outliers, or drift too large):
- Log the cause, including how many sources were dropped and why.
- Do not submit a new round; consumers keep reading the last on-chain value.
- **Staleness warning**: Track "time since last successful round" and emit a WARNING log if it exceeds a threshold (e.g., 10 minutes). No on-chain heartbeat needed—consumers can check `updatedAt` timestamp themselves.

### Cold Start (First Round)

On first run, `previous_price` is `None`:
- Drift limit does NOT apply to the first round (no previous price to compare against).
- To avoid garbage first price, require `MIN_SOURCES + 1` for the first round, or manually verify the first submission is reasonable.
- Alternative: Fetch last on-chain price from `latestRoundData()` if available and use that as `previous_price`.

### Timestamp Consistency

Different APIs have different data freshness (CoinGecko may lag 30s behind Coinbase):
- Accept this as inherent to aggregation—median smooths out minor timing differences.
- If strict freshness is required later, add per-source `max_age_seconds` config to reject stale responses.

### USDT Depeg Risk (Binance Conversion)

When using Binance (USDT pairs) with conversion:
- Monitor USDT/USD rate; if it deviates >2% from 1.0, skip Binance as a source for that round.
- Log a warning: "USDT depeg detected, excluding Binance from aggregation".

---

## 7. Implementation Order

1. **Phase 1**: Update contract comments in `PriceFeedDirectory.sol`
2. **Phase 2**: Implement core aggregation modules (`AggregatedPair`, `PriceAggregator`, `SourceManager`)
3. **Phase 3**: Create new fetcher module structure (`oracle/src/fetchers/`) and move HTTP logic there
4. **Phase 4**: Rewrite `PriceOracle.py` to use aggregated pairs, fetchers, and `SourceManager`
5. **Phase 5**: Update `main.py` CLI arguments and env defaults (`PAIRS`, `SOURCES`, etc.)
6. **Phase 6**: Update `.env.example`, `compose.yaml`, and `rofl.yaml` to the new configuration
7. **Phase 7**: Add unit tests for `AggregatedPair.compute_feed_hash`, `PriceAggregator`, and `SourceManager`
8. **Phase 8**: Integration test on `sapphire-localnet` with stub/fake fetchers
9. **Phase 9**: Dry-run against real APIs with a small set of pairs and sources

---

## 8. Recommended Default Configuration

For production with ROSE/USD support:

```env
PAIRS=btc/usd,eth/usd,rose/usd
SOURCES=coinbase,kraken,bitstamp,coingecko,coinmarketcap
MIN_SOURCES=2
MAX_DEVIATION_PERCENT=5.0
DRIFT_LIMIT_PERCENT=10.0
FETCH_PERIOD=60
SUBMIT_PERIOD=300            # 5 min; lower requires CMC paid API

# API keys
API_KEY_COINGECKO=           # Optional, increases rate limit
API_KEY_COINMARKETCAP=xxx    # Required for CoinMarketCap (free tier: 333 calls/day)
```

**Rationale:**
- Coinbase: Native USD, no API key, **supports ROSE/USD**
- Kraken, Bitstamp: Native USD, no API key (BTC/ETH only, no ROSE)
- CoinGecko: Supports all pairs including ROSE/USD (free tier sufficient)
- CoinMarketCap: Backup source for ROSE/USD redundancy (free tier covers our call volume at 5 min intervals)
- SUBMIT_PERIOD=300 (5 min): Stays within CMC free tier (288 calls/day < 333 limit)
- MIN_SOURCES=2: Ensures at least 2 confirmations before submission
- DRIFT_LIMIT_PERCENT=10.0: Prevents rounds that diverge too far from the last accepted median

**ROSE/USD coverage**: 3 sources (Coinbase + CoinGecko + CoinMarketCap) ensures redundancy if one fails.

---

## 9. Testing & Rollout Notes

- Add unit tests:
  - `AggregatedPair.compute_feed_hash` to ensure it matches the Solidity `PriceFeedDirectory` key scheme.
  - `PriceAggregator.aggregate` for:
    - normal scenarios,
    - heavy outlier presence,
    - drift-limit behavior,
    - handling of `None`/zero prices.
  - `SourceManager` backoff and recovery logic.
- Add an integration test for `PriceOracle` with fake fetchers to verify:
  - On-chain `SimpleAggregator` answers match expected aggregated values.
  - Round IDs and timestamps progress as expected.
- For initial deployment, it is acceptable to only run aggregated feeds (no legacy per-exchange feeds) since this is not yet production, but keep a note in docs on how to re-introduce single-exchange feeds later if needed.
