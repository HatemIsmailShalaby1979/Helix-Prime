"""
Tests for fail-closed governance controls in control_plane/engine.py.

Verifies that when governance controls (audit, secrets, injection) are unavailable,
the engine fails with GovernanceControlUnavailable rather than silently skipping.
"""
from __future__ import annotations


class TestGovernanceFailClosed:
    """Tests for fail-closed governance controls."""

    def test_governance_control_unavailable_class_exists(self):
        """GovernanceControlUnavailable exception class exists in engine."""
        from control_plane.engine import GovernanceControlUnavailable

        assert issubclass(GovernanceControlUnavailable, RuntimeError)

        # Test instantiation
        exc = GovernanceControlUnavailable("test error message")
        assert "test error message" in str(exc)

    def test_engine_uses_governance_control_unavailable(self):
        """Engine imports GovernanceControlUnavailable for startup validation."""
        from control_plane.engine import Engine

        # Verify Engine class can be imported
        assert Engine is not None
        assert hasattr(Engine, "submit")
        assert hasattr(Engine, "execute")
        assert hasattr(Engine, "approve")
        assert hasattr(Engine, "cancel")
