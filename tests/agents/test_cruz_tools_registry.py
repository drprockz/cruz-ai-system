"""
Tests for CRUZ tool-registry consistency (audit gap #1).

Every agent that CruzAgent can dispatch to (_TOOL_AGENT_MAP) must be
advertised to Claude in CRUZ_TOOLS. If a tool is dispatchable but not
advertised, Claude literally cannot invoke it — the agent is dead code
from the user's perspective.

This test class guards against that asymmetry regressing.
"""

from __future__ import annotations

from agents.cruz.cruz_agent import CRUZ_TOOLS, _TOOL_AGENT_MAP

# Built-in CRUZ tools handled inline (not delegated to a specialist agent).
# These are advertised in CRUZ_TOOLS but intentionally absent from
# _TOOL_AGENT_MAP — CruzAgent.process() dispatches them directly.
# Mac Controller tools (SP3) are service-level; dispatch in _dispatch_mac_tool.
# Web tools (SP4) are service-level; dispatched inline against services.browser.
_BUILTIN_TOOLS = {
    "record_pattern_observation",
    "mac_screenshot",
    "mac_clipboard_read",
    "mac_clipboard_write",
    "mac_open_app",
    "mac_notify",
    "web_search",
    "fetch_url",
}

# Dispatcher-style tools: routed via _TOOL_AGENT_MAP but use structured
# context (not a free-text `task` string). They inject `tool_name` into
# context["tool"] so the agent can route by operation. The `task` property
# is intentionally absent from their input_schema.
_DISPATCHER_TOOLS = {
    "calendar_create_event",
    "calendar_list_events",
    "calendar_find_free_slot",
}


class TestCruzToolRegistryConsistency:
    def test_every_mapped_agent_is_advertised(self):
        """No agent should exist in _TOOL_AGENT_MAP without a CRUZ_TOOLS entry."""
        tool_names = {t["name"] for t in CRUZ_TOOLS}
        mapped = set(_TOOL_AGENT_MAP.keys())
        hidden = mapped - tool_names
        assert not hidden, (
            f"Agents mapped in _TOOL_AGENT_MAP but hidden from Claude — "
            f"they cannot be invoked via tool_use: {sorted(hidden)}. "
            f"Add a corresponding entry to CRUZ_TOOLS."
        )

    def test_every_advertised_tool_has_a_dispatcher(self):
        """Guards the reverse: no CRUZ_TOOLS entry without a mapped agent.

        Built-in tools (handled inline by CruzAgent) are exempt.
        """
        tool_names = {t["name"] for t in CRUZ_TOOLS}
        mapped = set(_TOOL_AGENT_MAP.keys()) | _BUILTIN_TOOLS
        orphaned = tool_names - mapped
        assert not orphaned, (
            f"CRUZ_TOOLS advertises tools with no dispatcher in "
            f"_TOOL_AGENT_MAP: {sorted(orphaned)}. "
            f"Either wire the agent or remove the tool definition."
        )

    def test_all_five_formerly_missing_agents_are_advertised(self):
        """Regression guard for audit gap #1 (2026-04-14)."""
        tool_names = {t["name"] for t in CRUZ_TOOLS}
        for required in ("qt", "sentinel", "mark", "raw", "pulse"):
            assert required in tool_names, (
                f"Tool '{required}' missing from CRUZ_TOOLS — "
                f"Claude cannot invoke the {required.upper()} agent."
            )

    def test_tool_definitions_have_required_fields(self):
        """Each CRUZ_TOOLS entry must have name, description, input_schema.

        Delegated tools (those routed via _TOOL_AGENT_MAP) must additionally
        expose a `task` property — CruzAgent._dispatch_tool reads it. Built-in
        tools handled inline by CruzAgent may declare their own schema.
        Dispatcher-style tools (e.g. calendar_*) use structured context and
        are exempt from the `task` requirement.
        """
        for tool in CRUZ_TOOLS:
            assert "name" in tool, f"tool missing name: {tool}"
            assert "description" in tool, f"tool missing description: {tool['name']}"
            assert "input_schema" in tool, f"tool missing input_schema: {tool['name']}"
            schema = tool["input_schema"]
            assert schema.get("type") == "object", (
                f"{tool['name']}.input_schema.type must be 'object'"
            )
            if tool["name"] in _BUILTIN_TOOLS:
                continue
            if tool["name"] in _DISPATCHER_TOOLS:
                continue
            props = schema.get("properties", {})
            assert "task" in props, (
                f"{tool['name']}.input_schema.properties.task missing — "
                f"CruzAgent._dispatch_tool relies on tool_input.get('task')"
            )

    def test_tool_count_matches_agent_count(self):
        """Simple quantitative guard — delegated tools must mirror _TOOL_AGENT_MAP.

        Dispatcher-style tools (calendar_*) count as delegated: they ARE in
        _TOOL_AGENT_MAP even though they use structured context instead of `task`.
        """
        delegated = [t for t in CRUZ_TOOLS if t["name"] not in _BUILTIN_TOOLS]
        assert len(delegated) == len(_TOOL_AGENT_MAP), (
            f"CRUZ_TOOLS has {len(delegated)} delegated entries but "
            f"_TOOL_AGENT_MAP has {len(_TOOL_AGENT_MAP)} — they must be kept in sync."
        )


def test_mac_controller_tools_present() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    names = {t["name"] for t in CRUZ_TOOLS}
    expected = {
        "mac_screenshot",
        "mac_clipboard_read",
        "mac_clipboard_write",
        "mac_open_app",
        "mac_notify",
    }
    assert expected <= names, f"missing mac tools: {expected - names}"


def test_mac_clipboard_write_schema_requires_text() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    tool = next(t for t in CRUZ_TOOLS if t["name"] == "mac_clipboard_write")
    schema = tool["input_schema"]
    assert "text" in schema["required"]
    assert schema["properties"]["text"]["type"] == "string"


def test_mac_notify_schema_has_optional_sound() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    tool = next(t for t in CRUZ_TOOLS if t["name"] == "mac_notify")
    schema = tool["input_schema"]
    assert {"title", "body"} <= set(schema["required"])
    assert "sound" not in schema["required"]
    assert schema["properties"]["sound"]["type"] == "boolean"


def test_mac_screenshot_schema_has_optional_region() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    tool = next(t for t in CRUZ_TOOLS if t["name"] == "mac_screenshot")
    schema = tool["input_schema"]
    assert "region" in schema["properties"]
    assert schema["properties"]["region"]["type"] == "array"


def test_calendar_tools_present() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    names = {t["name"] for t in CRUZ_TOOLS}
    assert {"calendar_create_event", "calendar_list_events", "calendar_find_free_slot"} <= names


def test_calendar_create_event_schema() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    tool = next(t for t in CRUZ_TOOLS if t["name"] == "calendar_create_event")
    schema = tool["input_schema"]
    assert {"title", "start_iso", "end_iso"} <= set(schema["required"])
    assert "attendees" in schema["properties"]
    assert schema["properties"]["attendees"]["type"] == "array"


def test_calendar_find_free_slot_schema() -> None:
    from agents.cruz.cruz_agent import CRUZ_TOOLS
    tool = next(t for t in CRUZ_TOOLS if t["name"] == "calendar_find_free_slot")
    schema = tool["input_schema"]
    assert {"duration_minutes", "earliest_iso", "latest_iso"} <= set(schema["required"])


def test_calendar_in_tool_agent_map() -> None:
    from agents.cruz.cruz_agent import _TOOL_AGENT_MAP
    from agents.calendar.calendar_agent import CalendarAgent
    for tool in ("calendar_create_event", "calendar_list_events", "calendar_find_free_slot"):
        assert _TOOL_AGENT_MAP[tool] is CalendarAgent
