// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "forge-std/console.sol";
import { Subcall } from "@oasisprotocol/sapphire-contracts/contracts/Subcall.sol";

import { RoflAggregatorV3Interface } from "./RoflAggregatorV3Interface.sol";
import { SimpleAggregator } from "./SimpleAggregator.sol";

/**
 * A directory contract for ROFL-powered price aggregator feeds.
 * Primarily used for bootstrapping ROFL-powered price oracles.
 */
contract PriceFeedDirectory {
    bytes16 private constant HEX_DIGITS = "0123456789abcdef";

    error AggregatorExists(bytes32 key);
    error AggregatorRoflAppIdMismatch();

    event FeedAdded(address indexed aggregator, string appProviderChainPair);

    // Maps the hashed and lowercase hex-encoded app ID (without leading 0x) and providerChainPair
    // (which can be aggregated or per-provider) to the data feed.
    //
    // Key examples (aggregated multi-source feeds - recommended):
    // - keccak256("005a216eb7f450bcc1f534a7575fb33d611b463fa2/aggregated/btc/usd")
    // - keccak256("005a216eb7f450bcc1f534a7575fb33d611b463fa2/aggregated/eth/usd")
    // - keccak256("005a216eb7f450bcc1f534a7575fb33d611b463fa2/aggregated/rose/usd")
    //
    // Legacy per-exchange or DEX formats (still accepted):
    // - keccak256("005a216eb7f450bcc1f534a7575fb33d611b463fa2/bitstamp.net/btc/usd")
    // - keccak256("005a216eb7f450bcc1f534a7575fb33d611b463fa2/uniswap.org/polygon/native/1bfd67037b42cf73acf2047067bd4f2c47d9bfd6")
    // - keccak256("005a216eb7f450bcc1f534a7575fb33d611b463fa2/uniswap.org/base/833589fCD6eDb6E08f4c7C32D4f71b54bdA02913/1bfd67037b42cf73acf2047067bd4f2c47d9bfd6")
    mapping(bytes32 => RoflAggregatorV3Interface) public feeds;

    // List of public ROFL-powered aggregator contracts.
    string[] public discoverableFeeds;

    // Adds a new ROFL-powered price aggregator feed smart contract.
    // @param providerChainPair Hashed value of the exchange hostname + / + the
    //        trading pair.
    //        The trading pair is a lower case string defined as:
    //          - base currency + / + quote currency
    //          - chain name + / + input currency address + / + output currency
    //            address
    //        The currency address is a lower-case hex-encoded address of an
    //        ERC-20 contract without the leading "0x" or "native", if it's a
    //        native token.
    //        Examples:
    //          - "bitstamp.net/btc/usd"
    //          - "uniswap.org/polygon/native/1bfd67037b42cf73acf2047067bd4f2c47d9bfd6"
    //          - "uniswap.org/base/833589fCD6eDb6E08f4c7C32D4f71b54bdA02913/1bfd67037b42cf73acf2047067bd4f2c47d9bfd6"
    // @param agg (optional) App-specific price aggregator smart contract. If zero, a new SimpleAggregator instance will be created.
    // @param discoverable Add the price aggregator contract to a public list of discoverable price aggregators.
    function addFeed(string calldata providerChainPair, RoflAggregatorV3Interface agg, bool discoverable) external {
        bytes21 roflAppId = Subcall.getRoflAppId();

        if (address(agg) != address(0) && roflAppId != agg.getRoflAppId()) {
            revert AggregatorRoflAppIdMismatch();
        }

        // Convert roflAppId bytes to lowercase hex string (without 0x prefix).
        // Inspired by https://github.com/OpenZeppelin/openzeppelin-contracts/blob/92033fc08df1c8ebeb8046d084dd24e82ba9d065/contracts/utils/Strings.sol#L85
        bytes memory roflAppIdHex = new bytes(42);
        bytes21 roflAppIdBits = roflAppId;
        for (int8 i = 41; i >= 0; --i) {
            roflAppIdHex[uint8(i)] = HEX_DIGITS[uint168(roflAppIdBits) & 0xf];
            roflAppIdBits >>= 4;
        }

        // Create the key by combining roflAppIdHex with providerChainPair
        bytes32 key = keccak256(abi.encodePacked(roflAppIdHex, "/", providerChainPair));
        if (address(feeds[key]) != address(0)) {
            revert AggregatorExists(key);
        }

        // Deploy new contract, if instance not provided.
        if (address(agg)==address(0)) {
            agg = new SimpleAggregator(roflAppId);
        }

        feeds[key] = agg;

        string memory appProviderChainPair = string(abi.encodePacked(roflAppIdHex, "/", providerChainPair));
        if (discoverable) {
            discoverableFeeds.push(appProviderChainPair);
        }

        emit FeedAdded(address(agg), appProviderChainPair);
    }
}
