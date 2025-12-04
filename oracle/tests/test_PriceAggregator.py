"""Unit tests for PriceAggregator."""

import pytest

from oracle.src.PriceAggregator import AggregationResult, PriceAggregator


class TestPriceAggregatorInit:
    """Test PriceAggregator initialization."""

    def test_default_values(self) -> None:
        """Default values should be reasonable."""
        agg = PriceAggregator()
        assert agg.min_sources == 2
        assert agg.max_deviation_percent == 5.0
        assert agg.drift_limit_percent is None

    def test_custom_values(self) -> None:
        """Custom values should be stored."""
        agg = PriceAggregator(
            min_sources=3,
            max_deviation_percent=10.0,
            drift_limit_percent=5.0,
        )
        assert agg.min_sources == 3
        assert agg.max_deviation_percent == 10.0
        assert agg.drift_limit_percent == 5.0

    def test_invalid_min_sources(self) -> None:
        """min_sources < 1 should raise ValueError."""
        with pytest.raises(ValueError, match="min_sources must be at least 1"):
            PriceAggregator(min_sources=0)

    def test_invalid_max_deviation(self) -> None:
        """max_deviation_percent <= 0 should raise ValueError."""
        with pytest.raises(ValueError, match="max_deviation_percent must be positive"):
            PriceAggregator(max_deviation_percent=0)

        with pytest.raises(ValueError, match="max_deviation_percent must be positive"):
            PriceAggregator(max_deviation_percent=-1)

    def test_invalid_drift_limit(self) -> None:
        """drift_limit_percent <= 0 should raise ValueError."""
        with pytest.raises(ValueError, match="drift_limit_percent must be positive"):
            PriceAggregator(drift_limit_percent=0)

        with pytest.raises(ValueError, match="drift_limit_percent must be positive"):
            PriceAggregator(drift_limit_percent=-5)


class TestPriceAggregatorBasicAggregation:
    """Test basic aggregation scenarios."""

    def test_simple_median_odd(self) -> None:
        """Median of odd number of values."""
        agg = PriceAggregator(min_sources=2)
        result = agg.aggregate({"a": 100.0, "b": 101.0, "c": 102.0})

        assert result.success
        assert result.price == 101.0
        assert result.metadata["count"] == 3

    def test_simple_median_even(self) -> None:
        """Median of even number of values."""
        agg = PriceAggregator(min_sources=2)
        result = agg.aggregate({"a": 100.0, "b": 101.0})

        assert result.success
        assert result.price == 100.5
        assert result.metadata["count"] == 2

    def test_single_source_with_min_1(self) -> None:
        """Single source should work with min_sources=1."""
        agg = PriceAggregator(min_sources=1)
        result = agg.aggregate({"a": 100.0})

        assert result.success
        assert result.price == 100.0

    def test_sources_list_in_metadata(self) -> None:
        """Metadata should contain list of sources used."""
        agg = PriceAggregator(min_sources=2)
        result = agg.aggregate({"coinbase": 100.0, "kraken": 101.0})

        assert result.success
        assert set(result.metadata["sources"]) == {"coinbase", "kraken"}


class TestPriceAggregatorInsufficientSources:
    """Test insufficient source handling."""

    def test_empty_prices(self) -> None:
        """Empty prices dict should fail."""
        agg = PriceAggregator(min_sources=2)
        result = agg.aggregate({})

        assert not result.success
        assert result.error == "insufficient_sources"
        assert result.metadata["available"] == 0

    def test_all_none_prices(self) -> None:
        """All None prices should fail."""
        agg = PriceAggregator(min_sources=2)
        result = agg.aggregate({"a": None, "b": None, "c": None})

        assert not result.success
        assert result.error == "insufficient_sources"
        assert result.metadata["available"] == 0

    def test_all_zero_prices(self) -> None:
        """All zero prices should fail."""
        agg = PriceAggregator(min_sources=2)
        result = agg.aggregate({"a": 0.0, "b": 0.0})

        assert not result.success
        assert result.error == "insufficient_sources"

    def test_negative_prices_filtered(self) -> None:
        """Negative prices should be filtered out."""
        agg = PriceAggregator(min_sources=2)
        result = agg.aggregate({"a": -100.0, "b": 100.0, "c": 101.0})

        assert result.success
        assert result.price == 100.5
        assert result.metadata["count"] == 2

    def test_mixed_valid_invalid(self) -> None:
        """Mix of valid and invalid should work if enough valid."""
        agg = PriceAggregator(min_sources=2)
        result = agg.aggregate({
            "valid1": 100.0,
            "valid2": 101.0,
            "none": None,
            "zero": 0.0,
            "negative": -50.0,
        })

        assert result.success
        assert result.price == 100.5

    def test_insufficient_after_filtering_invalid(self) -> None:
        """Should fail if not enough valid sources after filtering."""
        agg = PriceAggregator(min_sources=2)
        result = agg.aggregate({"valid": 100.0, "none": None, "zero": 0.0})

        assert not result.success
        assert result.error == "insufficient_sources"
        assert result.metadata["available"] == 1


class TestPriceAggregatorOutlierDetection:
    """Test outlier detection functionality."""

    def test_outlier_excluded(self) -> None:
        """Outlier beyond deviation threshold should be excluded."""
        agg = PriceAggregator(min_sources=2, max_deviation_percent=5.0)

        # 100, 101, 200 -> median=101, 200 deviates ~98% from median
        result = agg.aggregate({"a": 100.0, "b": 101.0, "rogue": 200.0})

        assert result.success
        assert result.metadata["dropped"] == {"rogue": 200.0}
        assert "rogue" not in result.metadata["sources"]

    def test_multiple_outliers(self) -> None:
        """Multiple outliers should all be excluded."""
        agg = PriceAggregator(min_sources=2, max_deviation_percent=5.0)

        result = agg.aggregate({
            "a": 100.0,
            "b": 101.0,
            "c": 102.0,
            "rogue1": 50.0,
            "rogue2": 200.0,
        })

        assert result.success
        assert set(result.metadata["dropped"].keys()) == {"rogue1", "rogue2"}

    def test_too_many_outliers_fails(self) -> None:
        """Should fail if too many outliers leave insufficient sources."""
        agg = PriceAggregator(min_sources=2, max_deviation_percent=1.0)

        # With 1% deviation, 100 and 150 are both outliers from each other
        # median of [100, 150] = 125, both deviate 20% which is >1%
        result = agg.aggregate({"a": 100.0, "b": 150.0})

        assert not result.success
        assert result.error == "too_many_outliers"

    def test_borderline_deviation(self) -> None:
        """Price exactly at deviation threshold should be included."""
        agg = PriceAggregator(min_sources=2, max_deviation_percent=5.0)

        # median=100, 105 deviates exactly 5%
        result = agg.aggregate({"a": 100.0, "b": 105.0})

        assert result.success
        assert result.metadata["count"] == 2
        assert len(result.metadata["dropped"]) == 0

    def test_initial_median_in_metadata(self) -> None:
        """Initial median should be in metadata."""
        agg = PriceAggregator(min_sources=2, max_deviation_percent=5.0)
        result = agg.aggregate({"a": 100.0, "b": 102.0, "rogue": 200.0})

        assert result.success
        # Initial median includes rogue: median([100, 102, 200]) = 102
        assert result.metadata["initial_median"] == 102.0


class TestPriceAggregatorDriftLimiting:
    """Test drift limiting functionality."""

    def test_drift_within_limit(self) -> None:
        """Price within drift limit should succeed."""
        agg = PriceAggregator(min_sources=2, drift_limit_percent=10.0)
        result = agg.aggregate(
            {"a": 105.0, "b": 106.0},
            previous_price=100.0,
        )

        assert result.success
        # 5.5% drift is within 10% limit
        assert result.price == 105.5

    def test_drift_exceeds_limit(self) -> None:
        """Price exceeding drift limit should fail."""
        agg = PriceAggregator(min_sources=2, drift_limit_percent=10.0)
        result = agg.aggregate(
            {"a": 120.0, "b": 121.0},
            previous_price=100.0,
        )

        assert not result.success
        assert result.error == "drift_too_large"
        assert result.metadata["drift_percent"] == pytest.approx(20.5, rel=0.01)
        assert result.metadata["previous_price"] == 100.0
        assert result.metadata["candidate_price"] == 120.5

    def test_no_drift_check_without_previous(self) -> None:
        """No drift check if previous_price is None."""
        agg = PriceAggregator(min_sources=2, drift_limit_percent=10.0)
        result = agg.aggregate(
            {"a": 200.0, "b": 201.0},
            previous_price=None,  # First round
        )

        assert result.success
        assert result.price == 200.5

    def test_no_drift_check_if_disabled(self) -> None:
        """No drift check if drift_limit_percent is None."""
        agg = PriceAggregator(min_sources=2, drift_limit_percent=None)
        result = agg.aggregate(
            {"a": 200.0, "b": 201.0},
            previous_price=100.0,  # 100% change
        )

        assert result.success
        assert result.price == 200.5

    def test_drift_check_downward(self) -> None:
        """Drift check should work for price decreases."""
        agg = PriceAggregator(min_sources=2, drift_limit_percent=10.0)
        result = agg.aggregate(
            {"a": 80.0, "b": 81.0},
            previous_price=100.0,
        )

        assert not result.success
        assert result.error == "drift_too_large"
        # ~19.5% decrease


class TestAggregationResult:
    """Test AggregationResult properties."""

    def test_success_property(self) -> None:
        """success should be True when price is not None."""
        result = AggregationResult(price=100.0, metadata={"sources": ["a"]})
        assert result.success is True

        result = AggregationResult(price=None, metadata={"error": "test"})
        assert result.success is False

    def test_error_property(self) -> None:
        """error should return error string or None."""
        success_result = AggregationResult(price=100.0, metadata={"sources": ["a"]})
        assert success_result.error is None

        error_result = AggregationResult(
            price=None, metadata={"error": "insufficient_sources"}
        )
        assert error_result.error == "insufficient_sources"
