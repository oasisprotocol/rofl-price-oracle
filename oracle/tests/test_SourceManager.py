"""Unit tests for SourceManager."""

from unittest.mock import patch

from oracle.src.SourceManager import SourceManager, SourceStatus


class TestSourceManagerInit:
    """Test SourceManager initialization."""

    def test_init_with_sources(self) -> None:
        """Sources should be tracked from init."""
        manager = SourceManager(["a", "b", "c"])
        assert manager.sources == ["a", "b", "c"]
        assert len(manager.get_all_status()) == 3

    def test_init_empty_sources(self) -> None:
        """Empty sources list should work."""
        manager = SourceManager([])
        assert manager.sources == []
        assert manager.get_active_sources() == []

    def test_custom_backoff_values(self) -> None:
        """Custom backoff values should be stored."""
        manager = SourceManager(
            ["a"],
            base_backoff_seconds=10.0,
            max_backoff_seconds=60.0,
        )
        assert manager.base_backoff_seconds == 10.0
        assert manager.max_backoff_seconds == 60.0

    def test_initial_status(self) -> None:
        """Initial status should have zero failures."""
        manager = SourceManager(["a"])
        status = manager.get_source_status("a")

        assert status is not None
        assert status.consecutive_failures == 0
        assert status.backoff_until == 0.0
        assert status.total_failures == 0
        assert status.total_successes == 0


class TestSourceManagerFailures:
    """Test failure recording and backoff."""

    def test_first_failure_backoff(self) -> None:
        """First failure should use base backoff."""
        manager = SourceManager(["a"], base_backoff_seconds=5.0)
        backoff = manager.record_failure("a")

        assert backoff == 5.0
        status = manager.get_source_status("a")
        assert status.consecutive_failures == 1
        assert status.total_failures == 1

    def test_exponential_backoff(self) -> None:
        """Backoff should double with each consecutive failure."""
        manager = SourceManager(["a"], base_backoff_seconds=5.0)

        backoff1 = manager.record_failure("a")
        assert backoff1 == 5.0

        backoff2 = manager.record_failure("a")
        assert backoff2 == 10.0

        backoff3 = manager.record_failure("a")
        assert backoff3 == 20.0

        backoff4 = manager.record_failure("a")
        assert backoff4 == 40.0

    def test_max_backoff_cap(self) -> None:
        """Backoff should be capped at max_backoff_seconds."""
        manager = SourceManager(
            ["a"],
            base_backoff_seconds=100.0,
            max_backoff_seconds=150.0,
        )

        backoff1 = manager.record_failure("a")
        assert backoff1 == 100.0

        backoff2 = manager.record_failure("a")
        # Would be 200, but capped at 150
        assert backoff2 == 150.0

        backoff3 = manager.record_failure("a")
        assert backoff3 == 150.0

    def test_failure_unknown_source(self) -> None:
        """Recording failure for unknown source should create it."""
        manager = SourceManager(["a"])
        manager.record_failure("unknown")

        status = manager.get_source_status("unknown")
        assert status is not None
        assert status.consecutive_failures == 1


class TestSourceManagerSuccess:
    """Test success recording."""

    def test_success_resets_consecutive_failures(self) -> None:
        """Success should reset consecutive failures."""
        manager = SourceManager(["a"])

        manager.record_failure("a")
        manager.record_failure("a")
        assert manager.get_source_status("a").consecutive_failures == 2

        manager.record_success("a")
        status = manager.get_source_status("a")

        assert status.consecutive_failures == 0
        assert status.backoff_until == 0.0

    def test_success_tracks_total(self) -> None:
        """Success should increment total_successes."""
        manager = SourceManager(["a"])

        manager.record_success("a")
        manager.record_success("a")
        manager.record_success("a")

        status = manager.get_source_status("a")
        assert status.total_successes == 3

    def test_success_preserves_total_failures(self) -> None:
        """Success should not reset total_failures."""
        manager = SourceManager(["a"])

        manager.record_failure("a")
        manager.record_failure("a")
        manager.record_success("a")
        manager.record_failure("a")

        status = manager.get_source_status("a")
        assert status.total_failures == 3
        assert status.consecutive_failures == 1

    def test_success_unknown_source(self) -> None:
        """Recording success for unknown source should create it."""
        manager = SourceManager(["a"])
        manager.record_success("unknown")

        status = manager.get_source_status("unknown")
        assert status is not None
        assert status.total_successes == 1


class TestSourceManagerActiveSources:
    """Test active source filtering."""

    def test_all_active_initially(self) -> None:
        """All sources should be active initially."""
        manager = SourceManager(["a", "b", "c"])
        assert manager.get_active_sources() == ["a", "b", "c"]

    def test_failed_source_inactive(self) -> None:
        """Failed source should be inactive during backoff."""
        manager = SourceManager(["a", "b"], base_backoff_seconds=60.0)

        manager.record_failure("a")
        active = manager.get_active_sources()

        assert "a" not in active
        assert "b" in active

    @patch("oracle.src.SourceManager.time.time")
    def test_source_active_after_backoff(self, mock_time) -> None:
        """Source should be active after backoff period."""
        mock_time.return_value = 1000.0
        manager = SourceManager(["a"], base_backoff_seconds=10.0)

        manager.record_failure("a")
        # backoff_until = 1000 + 10 = 1010

        mock_time.return_value = 1005.0
        assert "a" not in manager.get_active_sources()

        mock_time.return_value = 1010.0  # Exactly at backoff_until
        assert "a" in manager.get_active_sources()

        mock_time.return_value = 1015.0
        assert "a" in manager.get_active_sources()


class TestSourceManagerHelpers:
    """Test helper methods."""

    def test_is_source_active(self) -> None:
        """is_source_active should check backoff status."""
        manager = SourceManager(["a"], base_backoff_seconds=60.0)

        assert manager.is_source_active("a") is True

        manager.record_failure("a")
        assert manager.is_source_active("a") is False

    def test_is_source_active_unknown(self) -> None:
        """is_source_active for unknown source should return False."""
        manager = SourceManager(["a"])
        assert manager.is_source_active("unknown") is False

    @patch("oracle.src.SourceManager.time.time")
    def test_get_backoff_remaining(self, mock_time) -> None:
        """get_backoff_remaining should return correct time."""
        mock_time.return_value = 1000.0
        manager = SourceManager(["a"], base_backoff_seconds=30.0)

        manager.record_failure("a")
        # backoff_until = 1030

        mock_time.return_value = 1010.0
        assert manager.get_backoff_remaining("a") == 20.0

        mock_time.return_value = 1030.0
        assert manager.get_backoff_remaining("a") == 0.0

        mock_time.return_value = 1050.0
        assert manager.get_backoff_remaining("a") == 0.0

    def test_get_backoff_remaining_unknown(self) -> None:
        """get_backoff_remaining for unknown source should return 0."""
        manager = SourceManager(["a"])
        assert manager.get_backoff_remaining("unknown") == 0.0

    def test_get_source_status_unknown(self) -> None:
        """get_source_status for unknown source should return None."""
        manager = SourceManager(["a"])
        assert manager.get_source_status("unknown") is None

    def test_get_all_status(self) -> None:
        """get_all_status should return copy of all statuses."""
        manager = SourceManager(["a", "b"])
        manager.record_failure("a")
        manager.record_success("b")

        all_status = manager.get_all_status()
        assert len(all_status) == 2
        assert all_status["a"].consecutive_failures == 1
        assert all_status["b"].total_successes == 1

        # Should be a copy
        all_status["a"] = SourceStatus()
        assert manager.get_source_status("a").consecutive_failures == 1


class TestSourceManagerMutation:
    """Test source list mutation methods."""

    def test_add_source(self) -> None:
        """add_source should add new source."""
        manager = SourceManager(["a"])
        manager.add_source("b")

        assert "b" in manager.sources
        assert manager.get_source_status("b") is not None

    def test_add_source_idempotent(self) -> None:
        """Adding existing source should not duplicate."""
        manager = SourceManager(["a"])
        manager.record_failure("a")

        manager.add_source("a")
        assert manager.sources.count("a") == 1
        # Status should be preserved
        assert manager.get_source_status("a").consecutive_failures == 1

    def test_remove_source(self) -> None:
        """remove_source should remove source and status."""
        manager = SourceManager(["a", "b"])
        manager.remove_source("a")

        assert "a" not in manager.sources
        assert manager.get_source_status("a") is None

    def test_remove_source_unknown(self) -> None:
        """Removing unknown source should not raise."""
        manager = SourceManager(["a"])
        manager.remove_source("unknown")  # Should not raise

    def test_reset_source(self) -> None:
        """reset_source should clear status."""
        manager = SourceManager(["a"])
        manager.record_failure("a")
        manager.record_failure("a")
        manager.record_success("a")  # total_successes = 1

        manager.reset_source("a")
        status = manager.get_source_status("a")

        assert status.consecutive_failures == 0
        assert status.total_failures == 0
        assert status.total_successes == 0
        assert status.backoff_until == 0.0

    def test_reset_all(self) -> None:
        """reset_all should clear all sources."""
        manager = SourceManager(["a", "b"])
        manager.record_failure("a")
        manager.record_failure("a")
        manager.record_success("b")

        manager.reset_all()

        for source in ["a", "b"]:
            status = manager.get_source_status(source)
            assert status.consecutive_failures == 0
            assert status.total_failures == 0


class TestSourceStatus:
    """Test SourceStatus dataclass."""

    def test_default_values(self) -> None:
        """Default values should be zeros."""
        status = SourceStatus()
        assert status.consecutive_failures == 0
        assert status.backoff_until == 0.0
        assert status.total_failures == 0
        assert status.total_successes == 0

    def test_custom_values(self) -> None:
        """Custom values should be stored."""
        status = SourceStatus(
            consecutive_failures=5,
            backoff_until=1234.5,
            total_failures=10,
            total_successes=100,
        )
        assert status.consecutive_failures == 5
        assert status.backoff_until == 1234.5
        assert status.total_failures == 10
        assert status.total_successes == 100
