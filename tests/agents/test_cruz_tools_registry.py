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
        """Guards the reverse: no CRUZ_TOOLS entry without a mapped agent."""
        tool_names = {t["name"] for t in CRUZ_TOOLS}
        mapped = set(_TOOL_AGENT_MAP.keys())
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
        """Each CRUZ_TOOLS entry must have name, description, input_schema.task."""
        for tool in CRUZ_TOOLS:
            assert "name" in tool, f"tool missing name: {tool}"
            assert "description" in tool, f"tool missing description: {tool['name']}"
            assert "input_schema" in tool, f"tool missing input_schema: {tool['name']}"
            schema = tool["input_schema"]
            assert schema.get("type") == "object", (
                f"{tool['name']}.input_schema.type must be 'object'"
            )
            props = schema.get("properties", {})
            assert "task" in props, (
                f"{tool['name']}.input_schema.properties.task missing — "
                f"CruzAgent._dispatch_tool relies on tool_input.get('task')"
            )

    def test_tool_count_matches_agent_count(self):
        """Simple quantitative guard — both maps should have the same size."""
        assert len(CRUZ_TOOLS) == len(_TOOL_AGENT_MAP), (
            f"CRUZ_TOOLS has {len(CRUZ_TOOLS)} entries but _TOOL_AGENT_MAP "
            f"has {len(_TOOL_AGENT_MAP)} — they must be kept in sync."
        )
