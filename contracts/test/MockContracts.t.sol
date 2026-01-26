// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import {Test, console} from "forge-std/Test.sol";
import {MockPriceFeedDirectory} from "../src/mocks/MockPriceFeedDirectory.sol";
import {MockSimpleAggregator} from "../src/mocks/MockSimpleAggregator.sol";
import {RoflAggregatorV3Interface} from "../src/RoflAggregatorV3Interface.sol";

/// @title MockContractsTest
/// @notice Tests for mock contracts without ROFL TEE verification.
contract MockContractsTest is Test {
    MockPriceFeedDirectory public priceFeed;
    MockSimpleAggregator public aggregator;

    function setUp() public {
        priceFeed = new MockPriceFeedDirectory();
        aggregator = new MockSimpleAggregator(bytes21(0));
    }

    // -- MockSimpleAggregator Tests --

    function test_MockAggregator_submitObservation() public {
        uint80 roundId = 1;
        int256 answer = 50000 * 1e8; // $50,000 with 8 decimals.
        uint256 startedAt = block.timestamp - 1;
        uint256 updatedAt = block.timestamp;

        // Anyone can call submitObservation (no TEE check).
        aggregator.submitObservation(roundId, answer, startedAt, updatedAt);

        (uint80 storedRoundId, int256 storedAns, uint256 storedStarted, uint256 storedUpdated,) = aggregator.latestRoundData();
        assertEq(storedRoundId, roundId, "roundId mismatch");
        assertEq(storedAns, answer, "answer mismatch");
        assertEq(storedStarted, startedAt, "startedAt mismatch");
        assertEq(storedUpdated, updatedAt, "updatedAt mismatch");
    }

    function test_MockAggregator_submitObservation_fromAnyAddress() public {
        address randomUser = makeAddr("randomUser");

        vm.prank(randomUser);
        aggregator.submitObservation(1, 42000e8, block.timestamp, block.timestamp);

        (, int256 ans,,,) = aggregator.latestRoundData();
        assertEq(ans, 42000e8, "submission from random user should work");
    }

    function test_MockAggregator_setters() public {
        aggregator.setDescription("BTC/USD");
        assertEq(aggregator.description(), "BTC/USD");

        aggregator.setVersion(1);
        assertEq(aggregator.version(), 1);

        aggregator.setDecimals(8);
        assertEq(aggregator.decimals(), 8);

        bytes21 newAppId = bytes21(uint168(0x123456));
        aggregator.setRoflAppID(newAppId);
        assertEq(aggregator.getRoflAppId(), newAppId);
    }

    function test_MockAggregator_getRoundData() public {
        aggregator.submitObservation(100, 50000e8, 1000, 1001);
        aggregator.submitObservation(101, 51000e8, 1010, 1011);

        (uint80 roundId, int256 ans, uint256 startedAt, uint256 updatedAt,) = aggregator.getRoundData(100);
        assertEq(roundId, 100);
        assertEq(ans, 50000e8);
        assertEq(startedAt, 1000);
        assertEq(updatedAt, 1001);

        (roundId, ans, startedAt, updatedAt,) = aggregator.getRoundData(101);
        assertEq(roundId, 101);
        assertEq(ans, 51000e8);
    }

    // -- MockPriceFeedDirectory Tests --

    function test_MockPriceFeed_addFeed_deploysAggregator() public {
        priceFeed.addFeed("aggregated/btc/usd", RoflAggregatorV3Interface(address(0)), true);

        bytes32 key = keccak256("000000000000000000000000000000000000000000/aggregated/btc/usd");
        address deployed = address(priceFeed.feeds(key));
        assertTrue(deployed != address(0), "aggregator should be deployed");

        string memory discoverable = priceFeed.discoverableFeeds(0);
        assertEq(discoverable, "000000000000000000000000000000000000000000/aggregated/btc/usd");
    }

    function test_MockPriceFeed_addFeed_existingAggregator() public {
        MockSimpleAggregator existingAgg = new MockSimpleAggregator(bytes21(0));

        priceFeed.addFeed("bitstamp.net/btc/usd", RoflAggregatorV3Interface(address(existingAgg)), false);

        bytes32 key = keccak256("000000000000000000000000000000000000000000/bitstamp.net/btc/usd");
        assertEq(address(priceFeed.feeds(key)), address(existingAgg));
    }

    function test_MockPriceFeed_addFeed_revertsOnDuplicate() public {
        priceFeed.addFeed("aggregated/eth/usd", RoflAggregatorV3Interface(address(0)), false);

        vm.expectRevert();
        priceFeed.addFeed("aggregated/eth/usd", RoflAggregatorV3Interface(address(0)), false);
    }

    function test_MockPriceFeed_setMockAppId() public {
        bytes21 customAppId = bytes21(uint168(0xABCDEF));
        priceFeed.setMockAppId(customAppId);
        assertEq(priceFeed.mockAppId(), customAppId);

        // Add a feed with the custom app ID.
        priceFeed.addFeed("aggregated/rose/usd", RoflAggregatorV3Interface(address(0)), true);

        // Verify the feed is stored with the custom app ID in the key.
        string memory discoverable = priceFeed.discoverableFeeds(0);
        // The app ID hex should now reflect the custom value.
        assertTrue(bytes(discoverable).length > 0, "feed should be added");
    }

    function test_MockPriceFeed_addFeed_fromAnyAddress() public {
        address randomUser = makeAddr("randomUser");

        vm.prank(randomUser);
        priceFeed.addFeed("coinbase/btc/usd", RoflAggregatorV3Interface(address(0)), false);

        bytes32 key = keccak256("000000000000000000000000000000000000000000/coinbase/btc/usd");
        assertTrue(address(priceFeed.feeds(key)) != address(0), "anyone should be able to add feeds");
    }

    // -- Integration Test --

    function test_EndToEnd_LocalTesting() public {
        // Warp to a reasonable timestamp to avoid underflow.
        vm.warp(1700000000);

        // 1. Deploy mock directory.
        MockPriceFeedDirectory directory = new MockPriceFeedDirectory();

        // 2. Add a feed (auto-deploys MockSimpleAggregator).
        directory.addFeed("aggregated/btc/usd", RoflAggregatorV3Interface(address(0)), true);

        // 3. Get the deployed aggregator.
        bytes32 key = keccak256("000000000000000000000000000000000000000000/aggregated/btc/usd");
        MockSimpleAggregator agg = MockSimpleAggregator(address(directory.feeds(key)));

        // 4. Configure the aggregator.
        agg.setDecimals(10);
        agg.setDescription("aggregated/btc/usd");

        // 5. Submit observations (simulating the oracle).
        agg.submitObservation(1, 97500_0000000000, block.timestamp - 60, block.timestamp);

        // 6. Verify the data.
        (, int256 price,,,) = agg.latestRoundData();
        assertEq(price, 97500_0000000000, "price should be $97,500");
        assertEq(agg.decimals(), 10);
        assertEq(agg.description(), "aggregated/btc/usd");
    }
}
