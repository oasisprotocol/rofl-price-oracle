"""PriceOracle: Main orchestrator for off-chain aggregated price feeds.

This module fetches prices from multiple API sources, aggregates them using
median with outlier detection, and submits the aggregated price on-chain.

Architecture:
    - One observation loop per trading pair (e.g., btc/usd)
    - Each loop queries all configured sources concurrently
    - Prices are aggregated via median with outlier filtering
    - Failed sources enter exponential backoff
    - Aggregated prices are accumulated as observations
    - Observations are submitted on-chain every submit_period
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from .AggregatedPair import AggregatedPair
from .ContractUtility import ContractUtility
from .fetchers import BaseFetcher, get_available_fetchers, get_fetcher
from .PriceAggregator import PriceAggregator
from .RoflUtility import RoflUtility, bech32_to_bytes
from .RoflUtilityAppd import RoflUtilityAppd
from .RoflUtilityLocalnet import RoflUtilityLocalnet
from .SourceManager import SourceManager

if TYPE_CHECKING:
    from web3 import Web3
    from web3.contract import Contract

logger = logging.getLogger(__name__)

# Predeployed price directory contract addresses based on the network.
DEFAULT_PRICE_FEED_ADDRESS: dict[str, str | None] = {
    "sapphire": None,
    "sapphire-testnet": "0xB3E8721A5E9bb84Cfa99b50131Ac47341B4a9EfF",
    "sapphire-localnet": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
}

# Number of decimals stored on-chain.
NUM_DECIMALS = 10


class PriceOracle:
    """Main orchestrator for aggregated price feeds.

    Fetches prices from multiple sources, aggregates via median,
    and submits to on-chain aggregator contracts.

    :ivar network_name: Target network name.
    :ivar pairs: List of trading pairs to track.
    :ivar sources: List of price source names.
    :ivar fetch_period: Seconds between price fetches.
    :ivar submit_period: Seconds between on-chain submissions.
    :ivar min_sources: Minimum sources required for valid aggregation.
    :ivar max_deviation_percent: Max deviation before outlier exclusion.
    :ivar drift_limit_percent: Max change vs previous price.
    """

    def __init__(
        self,
        network_name: str,
        pairs: list[str],
        sources: list[str],
        price_feed_address: str | None = None,
        aggregator_addresses: list[str] | None = None,
        api_keys: dict[str, str] | None = None,
        fetch_period: int = 60,
        submit_period: int = 300,
        min_sources: int = 2,
        max_deviation_percent: float = 5.0,
        drift_limit_percent: float | None = 10.0,
        fetch_timeout: float = 10.0,
    ) -> None:
        """Initialize the price oracle.

        :param network_name: Network to connect to (sapphire, sapphire-testnet,
            sapphire-localnet).
        :param pairs: List of trading pairs (e.g., ["btc/usd", "eth/usd"]).
        :param sources: List of source names (e.g., ["coinbase", "kraken"]).
        :param price_feed_address: Address of PriceFeedDirectory contract.
        :param aggregator_addresses: Optional pre-deployed aggregator addresses.
        :param api_keys: Dict mapping source names to API keys.
        :param fetch_period: Seconds between price fetches (default: 60).
        :param submit_period: Seconds between on-chain submissions (default: 300).
        :param min_sources: Minimum sources required for aggregation (default: 2).
        :param max_deviation_percent: Max deviation from median before outlier
            exclusion (default: 5.0).
        :param drift_limit_percent: Max change vs previous price (default: 10.0,
            None to disable).
        :param fetch_timeout: Timeout for fetch requests (default: 10.0).
        :raises ValueError: If sources are invalid or no pairs specified.
        """
        self.network_name = network_name
        self.fetch_period = max(1, fetch_period)
        self.submit_period = max(6, submit_period)
        self.min_sources = min_sources
        self.max_deviation_percent = max_deviation_percent
        self.drift_limit_percent = drift_limit_percent
        self.fetch_timeout = fetch_timeout
        self.api_keys = api_keys or {}

        # Validate sources against registered fetchers
        available = get_available_fetchers()
        invalid = [s for s in sources if s not in available]
        if invalid:
            raise ValueError(f"Unknown sources: {invalid}. Available: {available}")
        self.sources = sources

        # Parse pairs
        self.pairs: list[AggregatedPair] = []
        for pair_str in pairs:
            try:
                self.pairs.append(AggregatedPair.from_string(pair_str))
            except ValueError as e:
                logger.error(f"Invalid pair format: {e}")
                raise

        if not self.pairs:
            raise ValueError("At least one trading pair must be specified")

        # Initialize contract utilities
        contract_utility = ContractUtility(network_name)
        self.w3: Web3 = contract_utility.w3

        # Load contract ABIs (static method call)
        self.aggregator_abi, self.aggregator_bytecode = ContractUtility.get_contract(
            "SimpleAggregator"
        )
        price_feed_abi, _ = ContractUtility.get_contract("PriceFeedDirectory")

        # Set up price feed directory contract
        if not price_feed_address:
            price_feed_address = DEFAULT_PRICE_FEED_ADDRESS.get(network_name)
        if not price_feed_address:
            raise ValueError(f"No price feed address for network {network_name}")

        self.price_feed_contract: Contract = self.w3.eth.contract(
            address=price_feed_address, abi=price_feed_abi
        )

        # Set up ROFL utility based on network
        self.rofl_utility: RoflUtility
        if network_name == "sapphire-localnet":
            self.rofl_utility = RoflUtilityLocalnet(self.w3)
        else:
            self.rofl_utility = RoflUtilityAppd()

        # Contract instances per pair
        self.contracts: dict[AggregatedPair, Contract] = {}

        # Pre-assign aggregator addresses if provided
        if aggregator_addresses:
            for i, addr in enumerate(aggregator_addresses):
                if i < len(self.pairs) and addr:
                    self.contracts[self.pairs[i]] = self.w3.eth.contract(
                        address=addr,
                        abi=self.aggregator_abi,
                        bytecode=self.aggregator_bytecode,
                    )

        # Create fetcher instances
        self.fetchers: dict[str, BaseFetcher] = {}
        for source in self.sources:
            api_key = self.api_keys.get(source)
            self.fetchers[source] = get_fetcher(source, api_key=api_key)

        # Precompute supported sources per pair so unsupported sources do not
        # get penalized via backoff for pairs they can never serve.
        self.pair_sources: dict[AggregatedPair, list[str]] = {}
        for pair in self.pairs:
            supported: list[str] = []
            for source in self.sources:
                fetcher = self.fetchers[source]
                try:
                    if fetcher.supports_pair(pair.pair_base, pair.pair_quote):
                        supported.append(source)
                except Exception as exc:  # Defensive: misbehaving fetcher
                    logger.warning(
                        f"[{source}] supports_pair({pair}) raised {exc}; "
                        "treating as unsupported"
                    )
            if not supported:
                raise ValueError(
                    f"No configured sources support pair {pair}. "
                    f"Sources: {self.sources}"
                )
            self.pair_sources[pair] = supported

        logger.info(
            f"PriceOracle initialized: pairs={[str(p) for p in self.pairs]}, "
            f"sources={self.sources}, fetch_period={self.fetch_period}s, "
            f"submit_period={self.submit_period}s"
        )

    def _detect_contract(self, pair: AggregatedPair, app_id_bytes: bytes) -> bool:
        """Detect existing aggregator contract for a pair.

        :param pair: Trading pair to detect contract for.
        :param app_id_bytes: 21-byte ROFL app ID.
        :returns: True if contract was found and registered.
        """
        feed_hash = pair.compute_feed_hash(app_id_bytes)
        address = self.price_feed_contract.functions.feeds(feed_hash).call()

        if address == "0x0000000000000000000000000000000000000000":
            return False

        contract = self.w3.eth.contract(
            address=address,
            abi=self.aggregator_abi,
            bytecode=self.aggregator_bytecode,
        )
        self.contracts[pair] = contract
        logger.info(f"Detected aggregator contract {address} for {pair}")

        # Sanity check and configure if needed
        decimals = contract.functions.decimals().call()
        description = contract.functions.description().call()

        if decimals == 0:
            tx_params = contract.functions.setDecimals(NUM_DECIMALS).build_transaction(
                {"gasPrice": self.w3.eth.gas_price}
            )
            result = self.rofl_utility.submit_tx(tx_params)
            logger.info(f"Set decimals to {NUM_DECIMALS}. Result: {result}")

        if not description:
            tx_params = contract.functions.setDescription(str(pair)).build_transaction(
                {"gasPrice": self.w3.eth.gas_price}
            )
            result = self.rofl_utility.submit_tx(tx_params)
            logger.info(f"Set description to {pair}. Result: {result}")

        return True

    def _deploy_contract(self, pair: AggregatedPair) -> bool:
        """Deploy a new aggregator contract for a pair via PriceFeedDirectory.

        :param pair: Trading pair to deploy contract for.
        :returns: True if deployment was submitted successfully.
        """
        tx_params = self.price_feed_contract.functions.addFeed(
            str(pair),  # "aggregated/btc/usd"
            "0x0000000000000000000000000000000000000000",  # Deploy new
            False,  # Not discoverable initially
        ).build_transaction({"gasPrice": self.w3.eth.gas_price})

        result = self.rofl_utility.submit_tx(tx_params)
        logger.info(f"Contract deploy submitted for {pair}. Result: {result}")
        return True

    def detect_or_deploy_contract(self, pair: AggregatedPair) -> None:
        """Ensure an aggregator contract exists for the pair.

        First attempts to detect existing contract, then deploys if not found.

        :param pair: Trading pair to ensure contract for.
        :raises RuntimeError: If contract cannot be detected or deployed.
        """
        if pair in self.contracts:
            return

        # Fetch the current app ID
        app_id = self.rofl_utility.fetch_appid()
        app_id_bytes = bech32_to_bytes(app_id)

        if self._detect_contract(pair, app_id_bytes):
            return

        # Deploy new contract
        self._deploy_contract(pair)

        # Try to detect again
        if self._detect_contract(pair, app_id_bytes):
            return

        logger.error(f"Failed to detect or deploy contract for {pair}")
        raise RuntimeError(f"Aggregator contract not available for {pair}")

    async def _fetch_with_timeout(
        self, source: str, base: str, quote: str
    ) -> float | None:
        """Fetch price from a source with timeout.

        :param source: Source name to fetch from.
        :param base: Base currency symbol.
        :param quote: Quote currency symbol.
        :returns: Price as float, or None on failure/timeout.
        """
        fetcher = self.fetchers.get(source)
        if not fetcher:
            return None

        if not fetcher.supports_pair(base, quote):
            return None

        try:
            return await asyncio.wait_for(
                fetcher.fetch(base, quote),
                timeout=self.fetch_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"[{source}] Timeout fetching {base}/{quote}")
            return None
        except Exception as e:
            logger.warning(f"[{source}] Error fetching {base}/{quote}: {e}")
            return None

    async def _aggregated_observation_loop(self, pair: AggregatedPair) -> None:
        """Main observation loop for an aggregated pair.

        Fetches from all sources, aggregates prices, accumulates observations,
        and submits on-chain periodically.

        :param pair: Trading pair to observe.
        """
        observations: list[tuple[int, int]] = []  # (price_scaled, timestamp)
        last_submit = time.time()

        contract = self.contracts[pair]
        decimals: int = contract.functions.decimals().call()
        latest_round_data = contract.functions.latestRoundData().call()
        round_id: int = latest_round_data[0]

        # Initialize aggregator and source manager
        aggregator = PriceAggregator(
            min_sources=self.min_sources,
            max_deviation_percent=self.max_deviation_percent,
            drift_limit_percent=self.drift_limit_percent,
        )
        pair_sources = self.pair_sources.get(pair, [])
        source_manager = SourceManager(pair_sources)

        # Track last good median for drift detection
        # On cold start, try to get last price from chain
        last_good_median: float | None = None
        if latest_round_data[1] > 0:  # answer > 0
            last_good_median = float(latest_round_data[1]) / (10**decimals)
            logger.info(f"{pair}: Starting with on-chain price ${last_good_median:.6f}")

        logger.info(
            f"Starting observation loop for {pair} "
            f"(decimals={decimals}, round_id={round_id})"
        )

        while True:
            # Get active sources (not in backoff) that support this pair
            active_sources = source_manager.get_active_sources()

            if not active_sources:
                logger.warning(f"{pair}: No active sources, sleeping...")
                await asyncio.sleep(self.fetch_period)
                continue

            # Fetch from all active sources concurrently
            tasks = [
                self._fetch_with_timeout(source, pair.pair_base, pair.pair_quote)
                for source in active_sources
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and update source manager
            prices: dict[str, float | None] = {}
            for source, result in zip(active_sources, results):
                if isinstance(result, BaseException):
                    logger.warning(f"[{source}] Exception: {result}")
                    backoff = source_manager.record_failure(source)
                    logger.debug(f"[{source}] Backoff for {backoff:.1f}s")
                elif result is None:
                    backoff = source_manager.record_failure(source)
                    logger.debug(f"[{source}] No price, backoff for {backoff:.1f}s")
                else:
                    source_manager.record_success(source)
                    prices[source] = result

            # Aggregate prices
            agg_result = aggregator.aggregate(prices, previous_price=last_good_median)

            if not agg_result.success:
                error_type = agg_result.error or "unknown"
                logger.warning(
                    f"{pair}: Aggregation failed ({error_type}): {agg_result.metadata}"
                )
                await asyncio.sleep(self.fetch_period)
                continue

            # Update last good median
            median_price = agg_result.price
            assert median_price is not None  # Guaranteed by agg_result.success
            last_good_median = median_price
            meta = agg_result.metadata

            # Log the aggregated price
            sources_used = meta.get("sources", [])
            dropped = list(meta.get("dropped", {}).keys())
            logger.info(
                f"{pair}: ${median_price:.6f} "
                f"(from {len(sources_used)} sources: {sources_used}"
                f"{f', dropped: {dropped}' if dropped else ''})"
            )

            # Accumulate observation
            price_scaled = int(median_price * (10**decimals))
            timestamp = int(time.time())
            observations.append((price_scaled, timestamp))

            # Check if it's time to submit
            if time.time() - last_submit > self.submit_period:
                round_id += 1

                # Take median of accumulated observations
                sorted_obs = sorted(observations)
                final_price = sorted_obs[len(observations) // 2][0]

                # Submit to chain
                tx_params = contract.functions.submitObservation(
                    round_id,
                    final_price,
                    observations[0][1],  # startedAt
                    observations[-1][1],  # updatedAt
                ).build_transaction({"gasPrice": self.w3.eth.gas_price})

                result = self.rofl_utility.submit_tx(tx_params)
                logger.info(
                    f"{pair}: Round {round_id} submitted "
                    f"(price=${final_price / 10**decimals:.6f}, "
                    f"observations={len(observations)}). Result: {result}"
                )

                last_submit = time.time()
                observations = []

            await asyncio.sleep(self.fetch_period)

    async def run(self) -> None:
        """Run the price oracle.

        Starts observation loops for all configured pairs and runs until
        interrupted.
        """
        tasks: list[asyncio.Task[None]] = []

        for pair in self.pairs:
            # Ensure contract exists
            self.detect_or_deploy_contract(pair)

            # Start observation loop
            tasks.append(asyncio.create_task(self._aggregated_observation_loop(pair)))

            # Small delay between starting loops to avoid thundering herd
            await asyncio.sleep(1)

        logger.info(f"Started {len(tasks)} observation loops")

        try:
            await asyncio.gather(*tasks)
        finally:
            # Clean up shared HTTP client
            await BaseFetcher.close_shared_client()
