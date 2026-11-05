"""Cold-start failures must be retried at the entry, before platforms load."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryNotReady

import custom_components.panasonic_smart_china as integration
from custom_components.panasonic_smart_china import fridge
from custom_components.panasonic_smart_china.profiles import find_profile_for_device_config


def entry():
    devices = {
        device_id: {"deviceName": device_id, "profile_id": "fridge_0100_fridge_43", "category": "0100"}
        for device_id in ["AABBCCDDEEFF_0100_Fridge-43", "112233445566_0100_Fridge-43"]
    }
    return SimpleNamespace(
        entry_id="entry", data={"usrId": "test", "SSID": "fake", "devices": devices}
    )


def prepare(monkeypatch, *, failure=None):
    refreshes = []
    cloud = SimpleNamespace(get_device_status=AsyncMock(return_value={"PCTempCur": 4}))

    class Coordinator:
        def __init__(self, hass, logger, *, update_method, **kwargs):
            self.data = None
            self.update_method = update_method

        async def async_config_entry_first_refresh(self):
            refreshes.append(self)
            if failure:
                raise failure
            await asyncio.sleep(0)
            self.data = await self.update_method()

    monkeypatch.setattr(integration, "_async_create_account_device", lambda *args: "parent")
    monkeypatch.setattr(integration, "PanasonicApiClient", lambda *args: cloud)
    monkeypatch.setattr(fridge, "DataUpdateCoordinator", Coordinator)
    return cloud, refreshes


def test_all_fridges_are_ready_before_platforms_and_share_the_first_read(monkeypatch):
    async def run():
        cloud, refreshes = prepare(monkeypatch)
        config_entry = entry()

        async def forward(actual_entry, platforms):
            runtime = hass.data["panasonic_smart_china"][actual_entry.entry_id]
            coordinators = runtime.get("fridge_coordinators", {})
            assert len(coordinators) == 2, "Both fridge reads must precede platform setup"
            assert all(coordinator.data for coordinator in coordinators.values())
            for _ in range(4):
                for device_id, config in actual_entry.data["devices"].items():
                    profile = find_profile_for_device_config(profile_id=config["profile_id"])
                    coordinator = await fridge.async_get_fridge_coordinator(
                        hass, actual_entry, {**actual_entry.data, **config, "deviceId": device_id}, profile, cloud
                    )
                    assert coordinator is coordinators[device_id]

        hass = SimpleNamespace(data={}, config_entries=SimpleNamespace(async_forward_entry_setups=forward))
        assert await integration.async_setup_entry(hass, config_entry)
        assert len(refreshes) == cloud.get_device_status.await_count == 2

    asyncio.run(run())


def test_failed_initial_read_retries_entry_without_forwarding_any_platform(monkeypatch):
    async def run():
        prepare(monkeypatch, failure=ConfigEntryNotReady("temporary cloud timeout"))
        forward = AsyncMock()
        hass = SimpleNamespace(data={}, config_entries=SimpleNamespace(async_forward_entry_setups=forward))
        with pytest.raises(ConfigEntryNotReady, match="temporary cloud timeout"):
            await integration.async_setup_entry(hass, entry())
        forward.assert_not_awaited()

    asyncio.run(run())
