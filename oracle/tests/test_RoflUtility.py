"""Unit tests for RoflUtility."""

import unittest

import pytest

from oracle.src.RoflUtility import bech32_to_bytes


class TestRoflUtility(unittest.TestCase):
    def test_bech32_to_bytes(self):
        """Test cases for the bech32_to_hex function"""
        # Test with a valid bech32 string
        # This is a sample - you'll need to replace with actual valid bech32 app_id
        app_id = "rofl1qrtetspnld9efpeasxmryl6nw9mgllr0euls3dwn"
        result = bech32_to_bytes(app_id)
        assert isinstance(result, bytes)
        assert len(result) == 21
        # Expected raw bytes result for the test bech32 string
        assert result == bytes.fromhex("00d795c033fb4b94873d81b6327f5371768ffc6fcf")

        # Test with invalid bech32 string
        with pytest.raises(ValueError, match="Invalid bech32 app_id"):
            bech32_to_bytes("invalid_bech32_string")

        # Test with empty string
        with pytest.raises(ValueError, match="Invalid bech32 app_id"):
            bech32_to_bytes("")

        # Test with malformed bech32 (valid format but invalid checksum)
        with pytest.raises(ValueError, match="Invalid bech32 app_id"):
            bech32_to_bytes("rofl1invalidchecksum")
