// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "forge-std/Script.sol";
import "../src/mocks/MockPriceFeedDirectory.sol";

/// @title DeployMocks
/// @notice Deploys mock contracts for local testing without ROFL TEE.
/// @dev Usage: forge script script/DeployMocks.s.sol --rpc-url http://localhost:8545 --broadcast
contract DeployMocks is Script {
    function run() external {
        // Use the first Anvil default account if no private key is set.
        uint256 deployerPrivateKey = vm.envOr(
            "PRIVATE_KEY",
            uint256(0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80)
        );

        vm.startBroadcast(deployerPrivateKey);

        MockPriceFeedDirectory priceFeed = new MockPriceFeedDirectory();
        console.log("MockPriceFeedDirectory deployed at:", address(priceFeed));

        // Optionally set a mock app ID if provided.
        bytes21 mockAppId = bytes21(vm.envOr("MOCK_APP_ID", bytes21(0)));
        if (mockAppId != bytes21(0)) {
            priceFeed.setMockAppId(mockAppId);
            console.log("Mock app ID set");
        }

        vm.stopBroadcast();
    }
}
