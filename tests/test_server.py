"""Tests for the MCP server itself: the tool registry and the reported version.

`server.py` used to be excluded from coverage, which meant the 15 `add_tool()`
calls — the single place where a tool's public name is decided — had no test at
all. A typo there is invisible to every other test (they import the tool
functions directly) and only surfaces as a missing tool in a client's
`tools/list` response.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from unittest.mock import patch

import pytest

from garmin_mcp_lite import server

# tool name -> (module that defines it, function name). Pinned deliberately: this
# is the contract clients see, so any rename has to be a conscious edit here.
EXPECTED_TOOLS: dict[str, tuple[str, str]] = {
    "garmin_activities": ("activities", "list_activities"),
    "garmin_activity_detail": ("activities", "get_activity_detail"),
    "garmin_training_plan": ("training", "get_training_plan"),
    "garmin_training_status": ("training", "get_training_status"),
    "garmin_health": ("health", "get_health_data"),
    "garmin_gear": ("gear", "get_gear_list"),
    "garmin_device": ("device", "get_device_info"),
    "garmin_hr_trend": ("hr_trend", "get_hr_trend"),
    "garmin_weekly_stats": ("weekly_stats", "get_weekly_stats"),
    "garmin_coach": ("coach", "get_coach_plans"),
    "garmin_events": ("events", "get_events"),
    "garmin_challenges": ("challenges", "get_challenges"),
    "garmin_race_prediction": ("race_prediction", "get_race_prediction"),
    "garmin_personal_records": ("records", "get_personal_records"),
    "garmin_zones": ("zones", "get_zones"),
}


def _tools() -> list:
    return server.mcp._tool_manager.list_tools()


class TestToolRegistry:
    def test_tool_count(self) -> None:
        assert len(_tools()) == len(EXPECTED_TOOLS)

    def test_tool_names_are_exactly_expected(self) -> None:
        registered = {t.name for t in _tools()}
        assert registered == set(EXPECTED_TOOLS)

    def test_no_duplicate_names(self) -> None:
        # The registry is a dict keyed by name, so a duplicated add_tool() call
        # silently overwrites instead of erroring — this catches that by count.
        names = [t.name for t in _tools()]
        assert len(names) == len(set(names))

    def test_names_use_garmin_prefix(self) -> None:
        assert all(t.name.startswith("garmin_") for t in _tools())

    def test_each_tool_wired_to_the_right_function(self) -> None:
        actual = {
            t.name: (t.fn.__module__.rsplit(".", 1)[-1], t.fn.__name__)
            for t in _tools()
        }
        assert actual == EXPECTED_TOOLS

    def test_every_tool_has_a_description(self) -> None:
        # FastMCP falls back to the docstring; a missing one means the model
        # cannot tell the tools apart and will pick the wrong one.
        for tool in _tools():
            assert tool.description, f"{tool.name} has no description"
            assert len(tool.description.strip()) >= 20, f"{tool.name} description too terse"

    def test_every_tool_exposes_a_valid_input_schema(self) -> None:
        for tool in _tools():
            schema = tool.parameters
            assert isinstance(schema, dict), f"{tool.name} schema is not a dict"
            assert schema.get("type") == "object", f"{tool.name} schema is not an object"
            props = schema.get("properties", {})
            assert isinstance(props, dict)
            for prop_name, prop in props.items():
                # Every property must tell a client how to serialise the value.
                assert any(k in prop for k in ("type", "anyOf", "oneOf", "allOf", "$ref", "enum")), (
                    f"{tool.name}.{prop_name} has no type information"
                )
            required = schema.get("required", [])
            assert set(required) <= set(props), f"{tool.name} requires undeclared properties"

    def test_tools_are_all_callable(self) -> None:
        for tool in _tools():
            assert callable(tool.fn), f"{tool.name} is not callable"

    def test_server_name(self) -> None:
        assert server.mcp.name == "garmin-mcp-lite"


class TestReportedVersion:
    """The server used to advertise the version of the `mcp` dependency."""

    def test_package_version_matches_installed_metadata(self) -> None:
        assert server._package_version() == version("garmin-mcp-lite")

    def test_package_version_falls_back_when_not_installed(self) -> None:
        with patch.object(server, "version", side_effect=PackageNotFoundError):
            assert server._package_version() == "0.0.0+unknown"

    def test_initialization_options_report_our_version(self) -> None:
        # InitializationOptions are built lazily inside run(), so the attribute
        # assigned at import time is what actually reaches the client.
        assert server.mcp._mcp_server.version == server._package_version()

    def test_version_is_not_the_mcp_dependency_version(self) -> None:
        if version("mcp") == server._package_version():
            pytest.skip("version collision; the assertion below is meaningless")
        assert server.mcp._mcp_server.version != version("mcp")


class TestEntryPoint:
    def test_main_runs_the_server(self) -> None:
        with patch.object(server.mcp, "run") as run:
            server.main()
        run.assert_called_once_with()
