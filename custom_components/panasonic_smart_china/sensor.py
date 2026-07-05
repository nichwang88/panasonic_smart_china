"""Read-only sensor probes for Panasonic Smart China devices."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval

from .api import PanasonicApiAuthError, PanasonicApiClient, PanasonicApiError
from .const import (
    CONF_CATEGORY,
    CONF_CONTROLLER_MODEL,
    CONF_DEVICE_ID,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_DEVICES,
    CONF_ENABLED,
    CONF_PROFILE_ID,
    CONF_SSID,
    CONF_TOKEN,
    CONF_USR_ID,
    DOMAIN,
)
from .models import ENTITY_KIND_FRIDGE_PROBE, PLATFORM_SENSOR
from .profiles import find_profile_for_device_config
from .token import DeviceTokenError, generate_device_token

_LOGGER = logging.getLogger(__name__)

POLLING_INTERVAL = timedelta(seconds=60)
MAX_RAW_ATTRIBUTE_CHARS = 6000


async def async_setup_entry(hass, entry, async_add_entities):
    """Create read-only sensor probes for enabled devices under an account entry."""
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
        entities.append(
            PanasonicFridgeProbeSensor(
                hass,
                entity_config,
                device_config.get(CONF_DEVICE_NAME, device_id),
                profile,
                client,
            )
        )

    async_add_entities(entities, update_before_add=True)


class PanasonicFridgeProbeSensor(SensorEntity):
    """Diagnostic read-only probe for Fridge-43 status payload discovery."""

    _attr_has_entity_name = True
    _attr_translation_key = "fridge_probe"

    def __init__(self, hass, config, name, profile, client):
        self._hass = hass
        self._usr_id = config[CONF_USR_ID]
        self._device_id = config[CONF_DEVICE_ID]
        self._model = config.get(CONF_DEVICE_MODEL) or config.get(CONF_CONTROLLER_MODEL)
        self._api = client
        self._profile = profile
        try:
            self._token = generate_device_token(self._device_id, profile.token_strategy)
        except DeviceTokenError:
            self._token = config[CONF_TOKEN]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=name,
            manufacturer="Panasonic",
            model=self._model,
            via_device=(DOMAIN, self._usr_id),
        )
        self._attr_name = f"{name} 状态探针"
        self._attr_unique_id = f"panasonic_smart_china_{self._device_id}_fridge_probe"
        self._attr_native_value = STATE_UNAVAILABLE
        self._attr_extra_state_attributes = {
            "category": config.get(CONF_CATEGORY),
            "model": self._model,
            "profile_id": profile.profile_id,
            "read_only": True,
        }
        self._available = False
        self._unsub_polling = None

    @property
    def should_poll(self):
        return False

    @property
    def available(self):
        return self._available

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._unsub_polling = async_track_time_interval(
            self._hass,
            self._async_update_interval_wrapper,
            POLLING_INTERVAL,
        )

    async def async_will_remove_from_hass(self):
        if self._unsub_polling:
            self._unsub_polling()
            self._unsub_polling = None
        await super().async_will_remove_from_hass()

    async def _async_update_interval_wrapper(self, now):
        await self.async_update()
        self.async_write_ha_state()

    async def async_update(self):
        """Fetch and expose the raw fridge status payload without writing controls."""
        base_attributes = {
            "category": self._attr_extra_state_attributes.get("category"),
            "model": self._model,
            "profile_id": self._profile.profile_id,
            "read_only": True,
        }
        try:
            status = await self._api.get_device_status(
                self._profile,
                self._usr_id,
                self._device_id,
                self._token,
            )
        except PanasonicApiAuthError as err:
            self._available = False
            self._attr_native_value = "auth_failed"
            self._attr_extra_state_attributes = {
                **base_attributes,
                "last_error": str(err),
            }
            raise ConfigEntryAuthFailed("Panasonic Smart China session expired") from err
        except PanasonicApiError as err:
            self._available = True
            self._attr_native_value = "error"
            self._attr_extra_state_attributes = {
                **base_attributes,
                "last_error": str(err),
            }
            _LOGGER.info("Fridge probe status fetch failed for %s: %s", self._device_id, err)
            return

        self._available = True
        self._attr_native_value = "ok"
        self._attr_extra_state_attributes = {
            **base_attributes,
            "status_keys": sorted(status.keys()),
            "raw_status": _truncate_nested(status),
        }


def _truncate_nested(value: Any) -> Any:
    """Keep diagnostic attributes reasonably small for Home Assistant state storage."""
    if isinstance(value, dict):
        return {
            str(key): _truncate_nested(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_truncate_nested(item) for item in value]
    if isinstance(value, str) and len(value) > MAX_RAW_ATTRIBUTE_CHARS:
        return f"{value[:MAX_RAW_ATTRIBUTE_CHARS]}...<truncated>"
    return value
