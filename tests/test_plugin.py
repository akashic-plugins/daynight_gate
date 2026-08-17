from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import shutil

import pytest

from agent.plugins.manager import PluginManager
from agent.plugins.generation_activity_host import ActivityHost
from agent.plugins.generation_proactive_host import (
    ProactiveActivityAdapter,
    ProactiveRuntimeBinding,
)
from agent.plugins.static_manifest import load_static_plugin_manifest
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
    plugin_root = tmp_path / "plugins"
    shutil.copytree(
        Path(__file__).parents[1],
        plugin_root / "daynight_gate",
        ignore=shutil.ignore_patterns(".git", "tests", "__pycache__"),
    )
    plugins_home = tmp_path / ".akashic-plugin"
    data_dir = tmp_path / "plugin-data/daynight_gate-builtin"
    data_dir.mkdir(parents=True)
    (data_dir / "config.local.toml").write_text(
        'start = "22:00"\nend = "23:00"\npass_probability = 0.33\nreason = "late_quiet"\n',
        encoding="utf-8",
    )
    manager = PluginManager(
        plugin_dirs=[plugin_root],
        event_bus=EventBus(),
        tool_registry=None,
        workspace=tmp_path,
        installed_cache_root=plugins_home / "cache",
    )
    adapter = ProactiveActivityAdapter(manager.composition_generation_host)
    activity = ActivityHost((adapter,))
    manager.bind_activity_host(activity)
    root = None
    try:
        await manager.load_all()
        snapshot = manager.current_snapshot
        assert snapshot is not None
        assert snapshot.proactive_component_catalog is not None
        binding = activity.active
        assert binding is not None
        proactive = binding.child_bindings["proactive_components"]
        assert isinstance(proactive, ProactiveRuntimeBinding)
        module = proactive.module("proactive.gate.daynight")
        lease = manager.snapshot_store.lease(snapshot.snapshot_id)
        try:
            frame = await module.transform(
                lease,
                ProactiveFrame(
                    input=ProactiveTickInput(
                        session_key="cli:test",
                        started_at=datetime(2026, 6, 28, 14, 30, tzinfo=UTC),
                    )
                ),
            )
        finally:
            await lease.release()
        assert frame.slots["proactive:gate:pass_probability"] == 0.33
        assert frame.slots["proactive:gate:reason"] == "late_quiet"
        root = snapshot.composition_root
        assert root is not None
    finally:
        await manager.terminate_all()
    assert activity.active is None
    assert root is not None
    assert root.receipt().effects == ()


def test_static_manifest_matches_pure_v3_module() -> None:
    root = Path(__file__).parents[1]
    manifest = load_static_plugin_manifest(root)

    assert manifest.name == "daynight_gate"
    assert manifest.version == "3.0.0"
    assert manifest.api_version == 3
    assert manifest.entrypoint == "plugin.py"
