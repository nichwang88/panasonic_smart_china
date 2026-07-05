"""Switch controls for Panasonic Smart China Fridge-43 devices."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PanasonicApiClient
from .const import (
    CONF_CATEGORY,
    CONF_CONTROLLER_MODEL,
    CONF_DEVICE_ID,
    CONF_DEVICES,
    CONF_ENABLED,
    CONF_PROFILE_ID,
    CONF_SSID,
    DOMAIN,
)
from .fridge import as_int, async_get_fridge_coordinator, is_on_value
from .models import ENTITY_KIND_FRIDGE_PROBE, PLATFORM_SWITCH
from .profiles import find_profile_for_device_config

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FridgeSwitchDescription(SwitchEntityDescription):
    """Description for a writable Fridge-43 switch."""

    turn_on_updates: dict[str, Any] | None = None


FRIDGE_SWITCHES = (
    FridgeSwitchDescription(
        key="quickFreeze",
        name="速冻",
        icon="mdi:snowflake",
    ),
    FridgeSwitchDescription(
        key="autoIcing",
        name="自动制冰",
        icon="mdi:ice-cube",
    ),
    FridgeSwitchDescription(
        key="freshFrozen",
        name="新鲜冻结",
        icon="mdi:snowflake",
    ),
    FridgeSwitchDescription(
        key="nanoe",
        name="Nanoe",
        icon="mdi:air-filter",
    ),
    FridgeSwitchDescription(
        key="SCS1DryStore",
        name="干燥臻藏",
        icon="mdi:water-off",
    ),
    FridgeSwitchDescription(
        key="PCMicroFreeze",
        name="-3℃微冻",
        icon="mdi:snowflake-thermometer",
        turn_on_updates={"PCMilkStore": 0},
    ),
    FridgeSwitchDescription(
        key="PCMilkStore",
        name="母乳珍藏",
        icon="mdi:baby-bottle",
        turn_on_updates={"PCMicroFreeze": 0},
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Create writable switch controls for enabled Fridge-43 devices."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    client = runtime.get("client") or PanasonicApiClient(hass, entry.data.get(CONF_SSID))
    devices = entry.data.get(CONF_DEVICES, {})

    entities = []
    for device_id, device_config in devices.items():
        if not device_config.get(CONF_ENABLED, True):
            continue

        profile = find_profile_for_device_config(
            profile_id=device_config.get(CONF_PROFILE_ID),
            controller_model=device_config.get(CONF_CONTROLLER_MODEL),
            category_id=device_config.get(CONF_CATEGORY),
        )
        if not profile or PLATFORM_SWITCH not in profile.ha_platforms:
            continue

        if profile.entity_kind != ENTITY_KIND_FRIDGE_PROBE:
            _LOGGER.error(
                "Switch entity kind %s not implemented for %s.",
                profile.entity_kind,
                device_id,
            )
            continue

        entity_config = {
            **entry.data,
            **device_config,
            CONF_DEVICE_ID: device_id,
        }
        coordinator = await async_get_fridge_coordinator(
            hass,
            entry,
            entity_config,
            profile,
            client,
        )
        entities.extend(
            PanasonicFridgeSwitch(coordinator, description)
            for description in FRIDGE_SWITCHES
        )

    async_add_entities(entities)


class PanasonicFridgeSwitch(CoordinatorEntity, SwitchEntity):
    """Writable Fridge-43 feature switch."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description: FridgeSwitchDescription) -> None:
        super().__init__(coordinator)
        self.fridge = coordinator.fridge
        self.entity_description = description
        self._attr_device_info = self.fridge.device_info
        self._attr_unique_id = (
            f"panasonic_smart_china_{self.fridge.device_id}_{description.key.lower()}_switch"
        )
        self._attr_suggested_object_id = (
            f"{self.fridge.device_name}_{description.key.lower()}"
        )
        self._attr_name = description.name
        self._attr_icon = description.icon

    @property
    def is_on(self) -> bool | None:
        return is_on_value((self.coordinator.data or {}).get(self.entity_description.key))

    async def async_turn_on(self, **kwargs: Any) -> None:
        updates = {self.entity_description.key: 1}
        if self.entity_description.key == "nanoe":
            scs_temp = as_int((self.coordinator.data or {}).get("SCS1TempSet"))
            if scs_temp is None or scs_temp <= 0:
                raise HomeAssistantError("Nanoe can only be enabled above 0℃")
        if self.entity_description.turn_on_updates:
            updates.update(self.entity_description.turn_on_updates)
        await self.fridge.async_set_status(updates)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.fridge.async_set_status({self.entity_description.key: 0})
        await self.coordinator.async_request_refresh()
