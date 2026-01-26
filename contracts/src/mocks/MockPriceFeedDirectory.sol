// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import { RoflAggregatorV3Interface } from "../RoflAggregatorV3Interface.sol";
import { MockSimpleAggregator } from "./MockSimpleAggregator.sol";

/// @title MockPriceFeedDirectory
/// @notice Testing version of PriceFeedDirectory without ROFL app ID verification.
/// @dev DO NOT USE IN PRODUCTION - anyone can add feeds.
contract MockPriceFeedDirectory {
    bytes16 private constant HEX_DIGITS = "0123456789abcdef";

    error AggregatorExists(bytes32 key);

    event FeedAdded(address indexed aggregator, string appProviderChainPair);

    // Maps the hashed and lowercase hex-encoded app ID (without leading 0x) and providerChainPair
    // to the data feed.
    mapping(bytes32 => RoflAggregatorV3Interface) public feeds;

    // List of public ROFL-powered aggregator contracts.
    string[] public discoverableFeeds;

    // Mock app ID to use for feed registration (configurable for testing).
    bytes21 public mockAppId;

    constructor() {
        // Default mock app ID (all zeros).
        mockAppId = bytes21(0);
    }

    /// @notice Set the mock app ID for testing different scenarios.
    /// @param _appId The app ID to use for subsequent addFeed calls.
    function setMockAppId(bytes21 _appId) external {
        mockAppId = _appId;
    }

    /// @notice Adds a new price aggregator feed smart contract.
    /// @param providerChainPair The exchange/aggregated + trading pair string.
    /// @param agg Optional pre-deployed aggregator. If zero, deploys MockSimpleAggregator.
    /// @param discoverable Add to public list of discoverable feeds.
    function addFeed(string calldata providerChainPair, RoflAggregatorV3Interface agg, bool discoverable) external {
        bytes21 roflAppId = mockAppId;

        // Convert roflAppId bytes to lowercase hex string (without 0x prefix).
        bytes memory roflAppIdHex = new bytes(42);
        bytes21 roflAppIdBits = roflAppId;
        for (int8 i = 41; i >= 0; --i) {
            roflAppIdHex[uint8(i)] = HEX_DIGITS[uint168(roflAppIdBits) & 0xf];
            roflAppIdBits >>= 4;
        }

        // Create the key by combining roflAppIdHex with providerChainPair.
        bytes32 key = keccak256(abi.encodePacked(roflAppIdHex, "/", providerChainPair));
        if (address(feeds[key]) != address(0)) {
            revert AggregatorExists(key);
        }

        // Deploy new MockSimpleAggregator if instance not provided.
        if (address(agg) == address(0)) {
            agg = new MockSimpleAggregator(roflAppId);
        }

        feeds[key] = agg;

        string memory appProviderChainPair = string(abi.encodePacked(roflAppIdHex, "/", providerChainPair));
        if (discoverable) {
            discoverableFeeds.push(appProviderChainPair);
        }

        emit FeedAdded(address(agg), appProviderChainPair);
    }
}
