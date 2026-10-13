"""Exercise real fridge control code with an in-memory cloud boundary."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

from custom_components.panasonic_smart_china import fridge as module
from custom_components.panasonic_smart_china.api import PanasonicApiAuthError
from custom_components.panasonic_smart_china.profiles.fridge_0100_fridge_43 import (
    FRIDGE_0100_FRIDGE_43_PROFILE,
)
from custom_components.panasonic_smart_china.switch import (
    FRIDGE_SWITCHES,
    PanasonicFridgeSwitch,
)


def status():
    data = dict.fromkeys(module.FRIDGE_SETTING_PARAMS, 0)
    data.update(PCTempSet=4, SCS1TempSet=4, FCTempSet=-18, autoIcing=1)
    return data


class Cloud:
    def __init__(self, data=None, *, apply=True, delay_reads=0):
        self.data = status() if data is None else deepcopy(data)
        self.writes = []
        self.apply = apply
        self.delay_reads = delay_reads
        self.pending = None
        self.reads = 0
        self.error = None

    async def get_device_status(self, *args):
        self.reads += 1
        if self.pending is not None:
            if self.delay_reads:
                self.delay_reads -= 1
            else:
                self.data.update(self.pending)
                self.pending = None
        snapshot = deepcopy(self.data)
        await asyncio.sleep(0)
        return snapshot

    async def set_device_status(self, *args):
        if self.error:
            raise self.error
        params = deepcopy(args[-1])
        self.writes.append(params)
        await asyncio.sleep(0)
        if self.apply:
            if self.delay_reads:
                self.pending = params
            else:
                self.data.update(params)
        return {}


def fridge(cloud, device_id="AABBCCDDEEFF_0100_Fridge-43"):
    return module.PanasonicFridgeData(
        None,
        {"usrId": "test", "deviceId": device_id, "deviceName": "Test fridge"},
        FRIDGE_0100_FRIDGE_43_PROFILE,
        cloud,
    )


@pytest.fixture(autouse=True)
def fast_confirmation(monkeypatch):
    monkeypatch.setattr(module, "COMMAND_CONFIRM_DELAY", 0, raising=False)


def test_concurrent_commands_preserve_both_changes():
    async def run():
        cloud = Cloud()
        device = fridge(cloud)
        await asyncio.gather(
            device.async_set_status({"PCTempSet": 5}),
            device.async_set_status({"autoIcing": 0}),
        )
        assert cloud.data["PCTempSet"] == 5
        assert cloud.data["autoIcing"] == 0
    asyncio.run(run())


@pytest.mark.parametrize("missing", ["PCTempSet", "bodyOffline", "bodyOperating", "autoIcing"])
def test_incomplete_status_never_writes(missing):
    data = status()
    del data[missing]
    cloud = Cloud(data)
    with pytest.raises(HomeAssistantError):
        asyncio.run(fridge(cloud).async_set_status({"autoIcing": 0}))
    assert cloud.writes == []


def test_empty_status_never_writes():
    cloud = Cloud({})
    with pytest.raises(HomeAssistantError):
        asyncio.run(fridge(cloud).async_set_status({"autoIcing": 0}))
    assert cloud.writes == []


@pytest.mark.parametrize("updates", [
    {"PCTempSet": 0}, {"FCTempSet": -30}, {"SCS1TempSet": 1.5},
    {"autoIcing": 2}, {"bodyOffline": 0}, {"PCTempSet": True},
])
def test_invalid_or_read_only_updates_never_write(updates):
    cloud = Cloud()
    with pytest.raises(HomeAssistantError):
        asyncio.run(fridge(cloud).async_set_status(updates))
    assert cloud.writes == []


@pytest.mark.parametrize("field", ["bodyOffline", "bodyOperating"])
def test_offline_or_local_operation_never_writes(field):
    data = status()
    data[field] = 1
    cloud = Cloud(data)
    with pytest.raises(HomeAssistantError):
        asyncio.run(fridge(cloud).async_set_status({"autoIcing": 0}))
    assert cloud.writes == []


def test_nanoe_uses_fresh_temperature_not_coordinator_cache():
    async def run():
        data = status()
        data["SCS1TempSet"] = -3
        cloud = Cloud(data)
        coordinator = SimpleNamespace(
            fridge=fridge(cloud), data=status(), async_request_refresh=AsyncMock()
        )
        description = next(d for d in FRIDGE_SWITCHES if d.key == "nanoe")
        switch = PanasonicFridgeSwitch(coordinator, description)
        with pytest.raises(HomeAssistantError):
            await switch.async_turn_on()
        assert cloud.writes == []
    asyncio.run(run())


def test_mutually_exclusive_modes_are_enforced_at_write_boundary():
    cloud = Cloud()
    cloud.data["PCMilkStore"] = 1
    asyncio.run(fridge(cloud).async_set_status({"PCMicroFreeze": 1}))
    assert cloud.data["PCMicroFreeze"] == 1
    assert cloud.data["PCMilkStore"] == 0


def test_confirmation_waits_for_delayed_cloud_state():
    cloud = Cloud(delay_reads=1)
    confirmed = asyncio.run(fridge(cloud).async_set_status({"PCTempSet": 5}))
    assert confirmed["PCTempSet"] == 5
    assert cloud.reads >= 3
    assert len(cloud.writes) == 1


def test_accepted_but_unapplied_command_reports_failure_without_resending():
    cloud = Cloud(apply=False)
    with pytest.raises(HomeAssistantError, match="confirm"):
        asyncio.run(fridge(cloud).async_set_status({"PCTempSet": 5}))
    assert len(cloud.writes) == 1
    assert cloud.reads <= 4


def test_optional_absent_fields_are_not_filled_with_zero():
    data = status()
    del data["SCB2TempSet"]
    cloud = Cloud(data)
    asyncio.run(fridge(cloud).async_set_status({"PCTempSet": 5}))
    assert "SCB2TempSet" not in cloud.writes[0]


def test_auth_error_propagates_and_releases_command_lock():
    async def run():
        cloud = Cloud()
        device = fridge(cloud)
        cloud.error = PanasonicApiAuthError("expired")
        with pytest.raises(ConfigEntryAuthFailed):
            await device.async_set_status({"autoIcing": 0})
        cloud.error = None
        await asyncio.wait_for(device.async_set_status({"autoIcing": 0}), timeout=1)
        assert cloud.data["autoIcing"] == 0
    asyncio.run(run())


@pytest.mark.parametrize("key,value", [
    ("PCTempSet", None), ("bodyOffline", "bad"), ("bodyOperating", 255),
    ("autoIcing", 1.5), ("FCTempSet", float("nan")),
])
def test_invalid_cloud_values_never_write(key, value):
    data = status()
    data[key] = value
    cloud = Cloud(data)
    with pytest.raises(HomeAssistantError):
        asyncio.run(fridge(cloud).async_set_status({"autoIcing": 0}))
    assert cloud.writes == []


def test_combined_update_cannot_enable_nanoe_below_zero():
    cloud = Cloud()
    with pytest.raises(HomeAssistantError):
        asyncio.run(fridge(cloud).async_set_status({"SCS1TempSet": -3, "nanoe": 1}))
    assert cloud.writes == []


def test_nanoe_can_be_disabled_while_lowering_temperature():
    cloud = Cloud()
    cloud.data["nanoe"] = 1
    asyncio.run(fridge(cloud).async_set_status({"SCS1TempSet": -3, "nanoe": 0}))
    assert cloud.data["SCS1TempSet"] == -3
    assert cloud.data["nanoe"] == 0


def test_switch_updates_coordinator_from_confirmed_readback():
    async def run():
        cloud = Cloud()
        observed = []
        coordinator = SimpleNamespace(
            fridge=fridge(cloud), data=status(), async_set_updated_data=observed.append
        )
        description = next(d for d in FRIDGE_SWITCHES if d.key == "quickFreeze")
        await PanasonicFridgeSwitch(coordinator, description).async_turn_on()
        assert observed[0]["quickFreeze"] == 1
        assert observed[0] == cloud.data
    asyncio.run(run())


def test_background_poll_waits_for_command_confirmation():
    async def run():
        cloud = Cloud(delay_reads=1)
        device = fridge(cloud)
        command = asyncio.create_task(device.async_set_status({"PCTempSet": 5}))
        await asyncio.sleep(0)
        observed = await device.async_poll_status()
        await command
        assert observed["PCTempSet"] == 5
    asyncio.run(run())


def test_fridge_device_identifiers_survive_parent_link():
    device = fridge(Cloud())
    before = device.device_info["identifiers"]
    device.account_device_id = "account-id"
    assert device.device_info["identifiers"] == before
    assert device.device_info["via_device_id"] == "account-id"
