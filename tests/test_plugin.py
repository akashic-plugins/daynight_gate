from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import shutil

import pytest

from agent.plugins.manager import PluginManager
from agent.plugins.registry import plugin_registry
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from plugin import DayNightGateConfig, DayNightGateModule
from proactive_v2.frame import ProactiveFrame, ProactiveTickInput


@pytest.mark.asyncio
async def test_daynight_gate_sets_probability_in_window() -> None:
    module = DayNightGateModule(DayNightGateConfig())
    frame = ProactiveFrame(
        input=ProactiveTickInput(
            session_key="cli:test",
            started_at=datetime(2026, 6, 27, 17, 30, tzinfo=UTC),
        )
    )
    await module.run(frame)
    assert frame.slots["proactive:gate:pass_probability"] == 0.15


@pytest.mark.asyncio
async def test_daynight_gate_ignores_time_outside_window() -> None:
    module = DayNightGateModule(DayNightGateConfig())
    frame = ProactiveFrame(
        input=ProactiveTickInput(
            session_key="cli:test",
            started_at=datetime(2026, 6, 28, 4, 0, tzinfo=UTC),
        )
    )
    await module.run(frame)
    assert "proactive:gate:pass_probability" not in frame.slots


@pytest.mark.asyncio
async def test_daynight_gate_loads_config_from_plugin_manager(tmp_path: Path) -> None:
    plugin_registry._handlers._handlers.clear()
    plugin_registry._classes.clear()
    plugin_registry._instances.clear()
    plugin_root = tmp_path / "plugins"
    shutil.copytree(
        Path(__file__).parents[1],
        plugin_root / "daynight_gate",
        ignore=shutil.ignore_patterns(".git", "tests", "__pycache__"),
    )
    manager = PluginManager(
        plugin_dirs=[plugin_root],
        event_bus=EventBus(),
        tool_registry=ToolRegistry(),
        workspace=tmp_path,
        plugin_configs={
            "daynight_gate": {
                "start": "22:00",
                "end": "23:00",
                "pass_probability": 0.33,
                "reason": "late_quiet",
            }
        },
    )
    await manager.load_all()
    frame = ProactiveFrame(
        input=ProactiveTickInput(
            session_key="cli:test",
            started_at=datetime(2026, 6, 28, 14, 30, tzinfo=UTC),
        )
    )
    await manager.proactive_modules[0].run(frame)
    assert frame.slots["proactive:gate:pass_probability"] == 0.33
    assert frame.slots["proactive:gate:reason"] == "late_quiet"
