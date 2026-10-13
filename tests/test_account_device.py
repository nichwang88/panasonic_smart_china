"""Preserve appliance identifiers while linking the account parent device."""

from types import SimpleNamespace

import pytest

from custom_components.panasonic_smart_china import climate
from custom_components.panasonic_smart_china.profiles import SUPPORTED_CONTROLLERS


def test_account_device_is_registered_before_platform_setup(monkeypatch):
    import asyncio
    import custom_components.panasonic_smart_china as integration
    calls = []
    registry = SimpleNamespace(async_get_or_create=lambda **kwargs: (calls.append(kwargs) or SimpleNamespace(id="account-id")))
    from homeassistant.helpers import device_registry as dr
    monkeypatch.setattr(dr, "async_get", lambda hass: registry)
    async def forward(entry, platforms):
        assert calls
        assert hass.data["panasonic_smart_china"][entry.entry_id]["account_device_id"] == "account-id"
    hass = SimpleNamespace(data={}, config_entries=SimpleNamespace(async_forward_entry_setups=forward))
    entry = SimpleNamespace(entry_id="entry", unique_id="user", title="Account", data={"usrId": "user", "SSID": "fake"})
    assert asyncio.run(integration.async_setup_entry(hass, entry))
    assert calls[0]["identifiers"] == {("panasonic_smart_china", "user")}


def test_climate_uses_registered_parent_id_without_changing_identifier():
    entity = climate.PanasonicBaseEntity.__new__(climate.PanasonicBaseEntity)
    entity._device_id = "test-device"
    entity._usr_id = "user"
    entity._attr_name = "Device"
    entity._model = "Model"
    entity._account_device_id = "account-id"
    info = entity.device_info
    assert info["identifiers"] == {("panasonic_smart_china", "test-device")}
    assert info["via_device_id"] == "account-id"
    assert "via_device" not in info


@pytest.mark.parametrize("profile_id", ["ducted_ac_0900", "bathroom_heater_0820_fv_rb20vl1"])
def test_existing_climate_adapters_construct_with_account_parent(profile_id):
    import asyncio
    profile = next(p for p in SUPPORTED_CONTROLLERS.values() if p.profile_id == profile_id)
    device_id = "AABBCCDDEEFF_" + next(iter(profile.category_ids)) + "_" + profile.controller_model
    config = {
        "deviceId": device_id, "deviceName": "Test", "usrId": "test", "token": "fake",
        "profile_id": profile.profile_id, "category": next(iter(profile.category_ids)),
    }
    hass = SimpleNamespace(data={"panasonic_smart_china": {"entry": {
        "client": object(), "account_device_id": "account-id",
    }}})
    entry = SimpleNamespace(entry_id="entry", data={"usrId": "test", "SSID": "fake", "devices": {device_id: config}})
    entities = []
    asyncio.run(climate.async_setup_entry(hass, entry, lambda added, **kwargs: entities.extend(added)))
    assert len(entities) == 1
    assert entities[0].device_info["via_device_id"] == "account-id"
    assert entities[0].unique_id == "panasonic_smart_china_" + device_id + "_climate"
