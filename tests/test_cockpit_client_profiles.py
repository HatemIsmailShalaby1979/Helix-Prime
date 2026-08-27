"""Unit tests for cockpit client profile lookups.

These tests ensure that engine call functions correctly retrieve
client profiles from CLIENTS and fail gracefully when a profile is missing.
"""

import sys
from pathlib import Path

# Add cockpit to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cockpit"))


class TestClientProfileLookups:
    """Tests for client profile resolution in cockpit engine callers."""

    def test_call_wfm_with_valid_client(self):
        """Verify call_wfm loads client profile without raising NameError."""
        from cockpit import CLIENTS, call_wfm

        client_name = next(iter(CLIENTS.keys()))
        _result, error = call_wfm(client_name)
        # We expect either a DataFrame result or an ImportError (engine not installed)
        # but NOT a NameError from undefined 'c'
        assert error is None or "ImportError" in error
        if error:
            assert "NameError" not in error

    def test_call_rta_with_valid_client(self):
        """Verify call_rta loads client profile without raising NameError."""
        from cockpit import CLIENTS, call_rta

        client_name = next(iter(CLIENTS.keys()))
        _result, error = call_rta(client_name)
        # We expect either a DataFrame result or an ImportError
        assert error is None or "ImportError" in error
        if error:
            assert "NameError" not in error

    def test_call_wfm_with_missing_client(self):
        """Verify call_wfm handles missing client gracefully."""
        from cockpit import call_wfm

        result, error = call_wfm("NonExistentClient")
        # Should not raise; should use empty dict defaults
        assert result is None or hasattr(result, "to_dict")
        # If there's an error, it should not be NameError
        if error:
            assert "NameError" not in error

    def test_call_rta_with_missing_client(self):
        """Verify call_rta handles missing client gracefully."""
        from cockpit import call_rta

        result, error = call_rta("NonExistentClient")
        # Should not raise; should use empty dict defaults
        assert result is None or hasattr(result, "to_dict")
        if error:
            assert "NameError" not in error

    def test_clients_dict_not_empty(self):
        """Ensure CLIENTS dict has at least one entry for tests."""
        from cockpit import CLIENTS

        assert len(CLIENTS) > 0
        assert isinstance(CLIENTS, dict)

    def test_client_profile_has_required_keys(self):
        """Validate that all client profiles contain expected keys."""
        from cockpit import CLIENTS

        required_keys = {
            "agents",
            "calls_per_day",
            "shrinkage",
            "avg_handle_time",
            "service_level",
            "attrition",
        }

        for client_name, profile in CLIENTS.items():
            missing = required_keys - set(profile.keys())
            assert not missing, (
                f"Client '{client_name}' missing keys: {missing}. "
                "All clients must have: agents, calls_per_day, shrinkage, "
                "avg_handle_time, service_level, attrition"
            )
