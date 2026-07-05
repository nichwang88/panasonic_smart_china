"""Read-only binary sensors for Panasonic Smart China Fridge-43 devices."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
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
from .fridge import async_get_fridge_coordinator, is_on_value
from .models import ENTITY_KIND_FRIDGE_PROBE, PLATFORM_BINARY_SENSOR
from .profiles import find_profile_for_device_config

_LOGGER = logging.getLogger(__name__)


class FridgeBinarySensorDescription(BinarySensorEntityDescription):
    """Description for a Fridge-43 binary sensor."""


FRIDGE_DOOR_SENSORS = (
    FridgeBinarySensorDescription(
        key="PCGate1",
        name="冷藏室门 1",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    FridgeBinarySensorDescription(
        key="PCGate2",
        name="冷藏室门 2",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    FridgeBinarySensorDescription(
        key="FCGate1",
        name="冷冻室门 1",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    FridgeBinarySensorDescription(
        key="FCGate2",
        name="冷冻室门 2",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    FridgeBinarySensorDescription(
        key="SCGate",
        name="变温室门",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    FridgeBinarySensorDescription(
        key="SCB1Gate",
        name="抽屉门 1",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    FridgeBinarySensorDescription(
        key="SCB2Gate",
        name="抽屉门 2",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
)

FRIDGE_STATUS_SENSORS = (
    FridgeBinarySensorDescription(
        key="bodyOffline",
        name="本体离线",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    FridgeBinarySensorDescription(
        key="bodyOperating",
        name="本体操作中",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    FridgeBinarySensorDescription(
        key="waterLack",
        name="缺水",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    FridgeBinarySensorDescription(
        key="quickFreeze",
        name="速冻",
        icon="mdi:snowflake",
    ),
    FridgeBinarySensorDescription(
        key="quickCooling",
        name="速冷",
        icon="mdi:snowflake-thermometer",
    ),
    FridgeBinarySensorDescription(
        key="quickicing",
        name="快速制冰",
        icon="mdi:ice-cube",
    ),
    FridgeBinarySensorDescription(
        key="autoIcing",
        name="自动制冰",
        icon="mdi:ice-cube",
    ),
    FridgeBinarySensorDescription(
        key="icingStop",
        name="停止制冰",
        icon="mdi:ice-cube-off",
    ),
    FridgeBinarySensorDescription(
        key="ecoMode",
        name="节能模式",
        icon="mdi:leaf",
    ),
    FridgeBinarySensorDescription(
        key="nanoe",
        name="Nanoe",
        icon="mdi:air-filter",
    ),
    FridgeBinarySensorDescription(
        key="freshFrozen",
        name="新鲜冻结",
        icon="mdi:snowflake",
    ),
    FridgeBinarySensorDescription(
        key="vacation",
        name="假日模式",
        icon="mdi:beach",
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Create read-only binary sensors for enabled devices under an account entry."""
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
        if not profile or PLATFORM_BINARY_SENSOR not in profile.ha_platforms:
            continue

        if profile.entity_kind != ENTITY_KIND_FRIDGE_PROBE:
            _LOGGER.error(
                "Binary sensor entity kind %s not implemented for %s.",
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
            PanasonicFridgeBinarySensor(coordinator, description)
            for description in (*FRIDGE_DOOR_SENSORS, *FRIDGE_STATUS_SENSORS)
        )

    async_add_entities(entities)


class PanasonicFridgeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor backed by a Fridge-43 status field."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description: FridgeBinarySensorDescription) -> None:
        super().__init__(coordinator)
        self.fridge = coordinator.fridge
        self.entity_description = description
        self._attr_device_info = self.fridge.device_info
        self._attr_unique_id = (
            f"panasonic_smart_china_{self.fridge.device_id}_{description.key.lower()}"
        )
        self._attr_suggested_object_id = (
            f"{self.fridge.device_name}_{description.key.lower()}"
        )
        self._attr_name = description.name
        self._attr_device_class = description.device_class
        self._attr_icon = description.icon

    @property
    def is_on(self) -> bool | None:
        return is_on_value((self.coordinator.data or {}).get(self.entity_description.key))
