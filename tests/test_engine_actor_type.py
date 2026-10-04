"""
Tests for the centralized actor-type helper in control_plane/engine.py
(Prompt C, sub-task 2).

The three previously hardcoded ("sami", "suby", "phili", "wili", "system")
tuples are replaced by one helper. These tests pin the behaviour that helper
must preserve.
"""
from __future__ import annotations

from control_plane.engine import _actor_type_enum, _actor_type_for
from security.identity import ActorType


def test_actor_type_for_known_agents_and_system():
    assert _actor_type_for("sami") == "agent"
    assert _actor_type_for("suby") == "agent"
    assert _actor_type_for("phili") == "agent"
    assert _actor_type_for("wili") == "agent"
    assert _actor_type_for("system") == "service"


def test_actor_type_for_substring_and_human_defaults():
    assert _actor_type_for("ops_agent") == "agent"
    assert _actor_type_for("SAMI") == "agent"
    assert _actor_type_for("manager_07") == "human"
    assert _actor_type_for("") == "human"


def test_actor_type_enum_mapping():
    assert _actor_type_enum("system") is ActorType.SERVICE
    assert _actor_type_enum("suby") is ActorType.AGENT
    assert _actor_type_enum("manager_07") is ActorType.HUMAN
