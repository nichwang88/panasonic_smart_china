"""Read-only sensors for Panasonic Smart China devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PanasonicApiClient
from .const import (
    CONF_CATEGORY,
    CONF_CONTROLLER_MODEL,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICES,
    CONF_ENABLED,
    CONF_PROFILE_ID,
    CONF_SSID,
    DOMAIN,
)
from .fridge import as_int, async_get_fridge_coordinator, truncate_nested
from .models import ENTITY_KIND_FRIDGE_PROBE, PLATFORM_SENSOR
from .profiles import find_profile_for_device_config

_LOGGER = logging.getLogger(__name__)


class FridgeSensorDescription(SensorEntityDescription):
    """Description for a Fridge-43 sensor."""


FRIDGE_TEMPERATURE_SENSORS = (
    FridgeSensorDescription(
        key="PCTempCur",
        name="冷藏室当前温度",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    FridgeSensorDescription(
        key="PCTempSet",
        name="冷藏室设定温度",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    FridgeSensorDescription(
        key="FCTempCur",
        name="冷冻室当前温度",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    FridgeSensorDescription(
        key="FCTempSet",
        name="冷冻室设定温度",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    FridgeSensorDescription(
        key="SCS1TempCur",
        name="变温室当前温度",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    FridgeSensorDescription(
        key="SCS1TempSet",
        name="变温室设定温度",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Create read-only sensors for enabled devices under an account entry."""
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
        if not profile or PLATFORM_SENSOR not in profile.ha_platforms:
            continue

        if profile.entity_kind != ENTITY_KIND_FRIDGE_PROBE:
            _LOGGER.error(
                "Sensor entity kind %s not implemented for %s.",
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
        entities.append(PanasonicFridgeProbeSensor(coordinator))
        entities.extend(
            PanasonicFridgeTemperatureSensor(coordinator, description)
            for description in FRIDGE_TEMPERATURE_SENSORS
        )

    async_add_entities(entities)


class PanasonicFridgeEntity(CoordinatorEntity):
    """Base entity for Fridge-43 read-only coordinator entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, suffix: str) -> None:
        super().__init__(coordinator)
        self.fridge = coordinator.fridge
        self._attr_device_info = self.fridge.device_info
        self._attr_unique_id = (
            f"panasonic_smart_china_{self.fridge.device_id}_{suffix}"
        )
        self._attr_suggested_object_id = f"{self.fridge.device_name}_{suffix}"


class PanasonicFridgeProbeSensor(PanasonicFridgeEntity, SensorEntity):
    """Diagnostic read-only probe for Fridge-43 status payload discovery."""

    _attr_name = "状态探针"
    _attr_translation_key = "fridge_probe"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "fridge_probe")

    @property
    def native_value(self) -> str:
        return "ok" if self.coordinator.last_update_success else "error"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        attributes = {
            "category": self.fridge.category,
            "model": self.fridge.model,
            "profile_id": self.fridge.profile.profile_id,
            "read_only": True,
        }
        if self.coordinator.last_update_success:
            attributes["status_keys"] = sorted(data.keys())
            attributes["raw_status"] = truncate_nested(data)
        elif self.coordinator.last_exception:
            attributes["last_error"] = str(self.coordinator.last_exception)
        return attributes


class PanasonicFridgeTemperatureSensor(PanasonicFridgeEntity, SensorEntity):
    """Numeric temperature sensor for Fridge-43 status fields."""

    def __init__(self, coordinator, description: FridgeSensorDescription) -> None:
        super().__init__(coordinator, description.key.lower())
        self.entity_description = description
        self._attr_name = description.name
        self._attr_device_class = description.device_class
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_icon = description.icon

    @property
    def native_value(self) -> int | None:
        return as_int((self.coordinator.data or {}).get(self.entity_description.key))
