// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import { RoflAggregatorV3Interface } from "../RoflAggregatorV3Interface.sol";

/// @title MockSimpleAggregator
/// @notice Testing version of SimpleAggregator without TEE verification.
/// @dev DO NOT USE IN PRODUCTION - anyone can submit observations.
contract MockSimpleAggregator is RoflAggregatorV3Interface {
    // Configuration.
    string public description;
    uint256 public version;
    uint8 public decimals;
    bytes21 private roflAppId;

    // Observations.
    struct Observation {
        uint80 roundId; // The round in which the answer was updated.
        int256 answer;  // Price for the pair in predefined decimals.
        uint256 startedAt; // The timestamp when the round started.
        uint256 updatedAt; // The timestamp when the answer was computed.
    }

    mapping(uint80 => Observation) public observations;
    uint80 public latestRoundId;

    constructor(bytes21 _roflAppID) {
        roflAppId = _roflAppID;
    }

    // Returns the App ID of ROFL.
    function getRoflAppId() external view returns (bytes21) {
        return roflAppId;
    }

    function submitObservation(uint80 _roundId, int256 _answer, uint256 _startedAt, uint256 _updatedAt) external {
        observations[_roundId] = Observation({
            roundId: _roundId,
            answer: _answer,
            startedAt: _startedAt,
            updatedAt: _updatedAt
        });

        if (_roundId > latestRoundId) {
            latestRoundId = _roundId;
        }
    }

    function setDescription(string memory _description) external {
        description = _description;
    }

    function setVersion(uint256 _version) external {
        version = _version;
    }

    function setDecimals(uint8 _decimals) external {
        decimals = _decimals;
    }

    function setRoflAppID(bytes21 _roflAppID) external {
        roflAppId = _roflAppID;
    }

    function getRoundData(uint80 _roundId) external view override returns (uint80 roundId, int256 ans, uint256 startedAt, uint256 updatedAt, uint80 answeredInRound) {
        return (_roundId, observations[_roundId].answer, observations[_roundId].startedAt, observations[_roundId].updatedAt, _roundId);
    }

    function latestRoundData() external view override returns (uint80 roundId, int256 ans, uint256 startedAt, uint256 updatedAt, uint80 answeredInRound) {
        return (latestRoundId, observations[latestRoundId].answer, observations[latestRoundId].startedAt, observations[latestRoundId].updatedAt, latestRoundId);
    }
}
