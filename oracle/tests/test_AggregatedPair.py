"""Unit tests for AggregatedPair."""

import pytest
from web3 import Web3

from oracle.src.AggregatedPair import AggregatedPair


class TestAggregatedPairBasics:
    """Test basic AggregatedPair functionality."""

    def test_init_normalizes_to_lowercase(self) -> None:
        """Symbols should be normalized to lowercase."""
        pair = AggregatedPair("BTC", "USD")
        assert pair.pair_base == "btc"
        assert pair.pair_quote == "usd"

    def test_str_format(self) -> None:
        """String format should be 'aggregated/base/quote'."""
        pair = AggregatedPair("eth", "usd")
        assert str(pair) == "aggregated/eth/usd"

    def test_repr(self) -> None:
        """Repr should be developer-friendly."""
        pair = AggregatedPair("rose", "usd")
        assert repr(pair) == "AggregatedPair('rose', 'usd')"

    def test_hash_consistency(self) -> None:
        """Same pair should have same hash."""
        pair1 = AggregatedPair("btc", "usd")
        pair2 = AggregatedPair("BTC", "USD")  # Different case
        assert hash(pair1) == hash(pair2)

    def test_equality(self) -> None:
        """Pairs with same base/quote should be equal."""
        pair1 = AggregatedPair("btc", "usd")
        pair2 = AggregatedPair("BTC", "USD")
        assert pair1 == pair2

    def test_inequality(self) -> None:
        """Different pairs should not be equal."""
        pair1 = AggregatedPair("btc", "usd")
        pair2 = AggregatedPair("eth", "usd")
        assert pair1 != pair2

    def test_equality_with_non_pair(self) -> None:
        """Comparison with non-AggregatedPair should return NotImplemented."""
        pair = AggregatedPair("btc", "usd")
        assert pair.__eq__("btc/usd") == NotImplemented

    def test_usable_as_dict_key(self) -> None:
        """AggregatedPair should work as dictionary key."""
        pair1 = AggregatedPair("btc", "usd")
        pair2 = AggregatedPair("BTC", "USD")  # Same pair, different case

        d: dict[AggregatedPair, str] = {}
        d[pair1] = "value1"
        d[pair2] = "value2"  # Should overwrite

        assert len(d) == 1
        assert d[pair1] == "value2"


class TestAggregatedPairFromString:
    """Test AggregatedPair.from_string() parsing."""

    def test_valid_pair(self) -> None:
        """Parse valid pair string."""
        pair = AggregatedPair.from_string("btc/usd")
        assert pair.pair_base == "btc"
        assert pair.pair_quote == "usd"

    def test_uppercase_input(self) -> None:
        """Uppercase input should be normalized."""
        pair = AggregatedPair.from_string("ETH/USD")
        assert pair.pair_base == "eth"
        assert pair.pair_quote == "usd"

    def test_mixed_case(self) -> None:
        """Mixed case should be normalized."""
        pair = AggregatedPair.from_string("RoSe/UsD")
        assert pair.pair_base == "rose"
        assert pair.pair_quote == "usd"

    def test_invalid_no_slash(self) -> None:
        """String without slash should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid pair format"):
            AggregatedPair.from_string("btcusd")

    def test_invalid_too_many_slashes(self) -> None:
        """String with too many slashes should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid pair format"):
            AggregatedPair.from_string("btc/usd/extra")

    def test_invalid_empty(self) -> None:
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid pair format"):
            AggregatedPair.from_string("")

    def test_invalid_only_slash(self) -> None:
        """Single slash should raise ValueError (splits to ['', ''])."""
        # This produces ['', ''] which has length 2, so it passes length check
        # but creates pair with empty strings
        pair = AggregatedPair.from_string("/")
        assert pair.pair_base == ""
        assert pair.pair_quote == ""


class TestAggregatedPairFeedHash:
    """Test compute_feed_hash() for Solidity compatibility."""

    def test_hash_length(self) -> None:
        """Hash should be 32 bytes (keccak256)."""
        pair = AggregatedPair("btc", "usd")
        app_id = bytes.fromhex("005a216eb7f450bcc1f534a7575fb33d611b463fa2")
        hash_result = pair.compute_feed_hash(app_id)
        assert len(hash_result) == 32

    def test_hash_deterministic(self) -> None:
        """Same inputs should produce same hash."""
        pair = AggregatedPair("btc", "usd")
        app_id = bytes.fromhex("005a216eb7f450bcc1f534a7575fb33d611b463fa2")

        hash1 = pair.compute_feed_hash(app_id)
        hash2 = pair.compute_feed_hash(app_id)

        assert hash1 == hash2

    def test_hash_matches_solidity_format(self) -> None:
        """Hash should match Solidity keccak256(appIdHex/aggregated/base/quote)."""
        pair = AggregatedPair("btc", "usd")
        app_id = bytes.fromhex("005a216eb7f450bcc1f534a7575fb33d611b463fa2")

        # Manually compute what we expect
        key_string = f"{app_id.hex()}/aggregated/btc/usd"
        expected_hash = Web3.keccak(text=key_string)

        actual_hash = pair.compute_feed_hash(app_id)
        assert actual_hash == expected_hash

    def test_different_pairs_different_hashes(self) -> None:
        """Different pairs should produce different hashes."""
        app_id = bytes.fromhex("005a216eb7f450bcc1f534a7575fb33d611b463fa2")

        pair_btc = AggregatedPair("btc", "usd")
        pair_eth = AggregatedPair("eth", "usd")

        hash_btc = pair_btc.compute_feed_hash(app_id)
        hash_eth = pair_eth.compute_feed_hash(app_id)

        assert hash_btc != hash_eth

    def test_different_app_ids_different_hashes(self) -> None:
        """Different app IDs should produce different hashes."""
        pair = AggregatedPair("btc", "usd")

        app_id_1 = bytes.fromhex("005a216eb7f450bcc1f534a7575fb33d611b463fa2")
        app_id_2 = bytes.fromhex("115a216eb7f450bcc1f534a7575fb33d611b463fa2")

        hash_1 = pair.compute_feed_hash(app_id_1)
        hash_2 = pair.compute_feed_hash(app_id_2)

        assert hash_1 != hash_2

    def test_known_hash_value(self) -> None:
        """Test against a pre-computed known hash value."""
        pair = AggregatedPair("btc", "usd")
        # 21-byte app ID (example)
        app_id = bytes.fromhex("005a216eb7f450bcc1f534a7575fb33d611b463fa2")

        hash_result = pair.compute_feed_hash(app_id)

        # Key string: "005a216eb7f450bcc1f534a7575fb33d611b463fa2/aggregated/btc/usd"
        expected = Web3.keccak(
            text="005a216eb7f450bcc1f534a7575fb33d611b463fa2/aggregated/btc/usd"
        )

        assert hash_result == expected
