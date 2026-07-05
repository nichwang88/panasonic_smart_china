"""Number controls for Panasonic Smart China Fridge-43 temperatures."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.const import UnitOfTemperature
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
from .fridge import as_int, async_get_fridge_coordinator
from .models import ENTITY_KIND_FRIDGE_PROBE, PLATFORM_NUMBER
from .profiles import find_profile_for_device_config

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FridgeNumberDescription(NumberEntityDescription):
    """Description for a writable Fridge-43 temperature number."""


FRIDGE_TEMPERATURE_NUMBERS = (
    FridgeNumberDescription(
        key="PCTempSet",
        name="冷藏室设定温度",
        icon="mdi:thermometer",
        native_min_value=2,
        native_max_value=7,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    FridgeNumberDescription(
        key="SCS1TempSet",
        name="变温室设定温度",
        icon="mdi:thermometer",
        native_min_value=-3,
        native_max_value=7,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    FridgeNumberDescription(
        key="FCTempSet",
        name="冷冻室设定温度",
        icon="mdi:thermometer",
        native_min_value=-23,
        native_max_value=-17,
        native_step=1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Create writable temperature numbers for enabled Fridge-43 devices."""
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
        if not profile or PLATFORM_NUMBER not in profile.ha_platforms:
            continue

        if profile.entity_kind != ENTITY_KIND_FRIDGE_PROBE:
            _LOGGER.error(
                "Number entity kind %s not implemented for %s.",
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
            PanasonicFridgeTemperatureNumber(coordinator, description)
            for description in FRIDGE_TEMPERATURE_NUMBERS
        )

    async_add_entities(entities)


class PanasonicFridgeTemperatureNumber(CoordinatorEntity, NumberEntity):
    """Writable Fridge-43 set temperature number."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description: FridgeNumberDescription) -> None:
        super().__init__(coordinator)
        self.fridge = coordinator.fridge
        self.entity_description = description
        self._attr_device_info = self.fridge.device_info
        self._attr_unique_id = (
            f"panasonic_smart_china_{self.fridge.device_id}_{description.key.lower()}_number"
        )
        self._attr_suggested_object_id = (
            f"{self.fridge.device_name}_{description.key.lower()}_control"
        )
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_native_min_value = description.native_min_value
        self._attr_native_max_value = description.native_max_value
        self._attr_native_step = description.native_step
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement

    @property
    def native_value(self) -> int | None:
        return as_int((self.coordinator.data or {}).get(self.entity_description.key))

    async def async_set_native_value(self, value: float) -> None:
        set_value = int(value)
        await self.fridge.async_set_status({self.entity_description.key: set_value})
        await self.coordinator.async_request_refresh()
