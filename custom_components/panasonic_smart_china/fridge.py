"""Shared helpers for Panasonic Fridge-43 read-only entities."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PanasonicApiAuthError, PanasonicApiClient, PanasonicApiError
from .const import (
    CONF_CATEGORY,
    CONF_CONTROLLER_MODEL,
    CONF_DEVICE_ID,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_NAME,
    CONF_SSID,
    CONF_TOKEN,
    CONF_USR_ID,
    DOMAIN,
)
from .models import PanasonicProfile
from .token import DeviceTokenError, generate_device_token

_LOGGER = logging.getLogger(__name__)

POLLING_INTERVAL = timedelta(seconds=60)
MAX_RAW_ATTRIBUTE_CHARS = 6000
FRIDGE_SETTING_PARAMS = (
    "PCTempSet",
    "PCTempCur",
    "PCTempCurAlarm",
    "SCS1TempSet",
    "SCS1TempCur",
    "SCS1TempCurAlarm",
    "SCS2TempSet",
    "SCS2TempCur",
    "SCS2TempCurAlarm",
    "SCB1TempSet",
    "SCB1TempCur",
    "SCB1TempCurAlarm",
    "SCB2TempSet",
    "SCB2TempCur",
    "SCB2TempCurAlarm",
    "FCTempSet",
    "FCTempCur",
    "FCTempCurAlarm",
    "quickFreeze",
    "vacation",
    "quickicing",
    "icingStop",
    "icingDeice",
    "eraseOdor",
    "ecoNaviSet",
    "ecoNaviCur",
    "speed",
    "RAModeCur",
    "SAModeCur",
    "bodyOperating",
    "iceDetection",
    "waterLack",
    "silver",
    "preservation",
    "nanoe",
    "freshFrozen",
    "smartHumi",
    "autoIcing",
    "WCModeCur",
    "forcedDeforst",
    "sevenFresh",
    "SCB1ModeCur",
    "SCB2ModeCur",
    "PCGate1",
    "PCGate2",
    "SCGate",
    "SCB1Gate",
    "SCB2Gate",
    "FCGate1",
    "FCGate2",
    "ICGate",
    "gateAlarm",
    "ecoMode",
    "bodyOffline",
    "voiceOperating",
    "SCB1NanoMode",
    "SCB2NanoMode",
    "PCMilkStore",
    "SCS1DryStore",
    "PCMicroFreeze",
)


class PanasonicFridgeData:
    """Runtime data for a single Panasonic Fridge-43 device."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        profile: PanasonicProfile,
        client: PanasonicApiClient,
    ) -> None:
        self.hass = hass
        self.profile = profile
        self.client = client
        self.usr_id = config[CONF_USR_ID]
        self.device_id = config[CONF_DEVICE_ID]
        self.device_name = config.get(CONF_DEVICE_NAME, self.device_id)
        self.category = config.get(CONF_CATEGORY)
        self.model = config.get(CONF_DEVICE_MODEL) or config.get(CONF_CONTROLLER_MODEL)
        try:
            self.token = generate_device_token(self.device_id, profile.token_strategy)
        except DeviceTokenError:
            self.token = config[CONF_TOKEN]

    @property
    def device_info(self) -> DeviceInfo:
        """Return Home Assistant device metadata."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=self.device_name,
            manufacturer="Panasonic",
            model=self.model,
        )

    async def async_fetch_status(self) -> dict[str, Any]:
        """Fetch the current fridge status payload."""
        try:
            return await self.client.get_device_status(
                self.profile,
                self.usr_id,
                self.device_id,
                self.token,
            )
        except PanasonicApiAuthError as err:
            raise ConfigEntryAuthFailed("Panasonic Smart China session expired") from err
        except PanasonicApiError as err:
            raise UpdateFailed(str(err)) from err

    async def async_set_status(self, updates: dict[str, Any]) -> None:
        """Write a small validated update using the fridge web app payload shape."""
        unknown_keys = set(updates) - set(FRIDGE_SETTING_PARAMS)
        if unknown_keys:
            raise HomeAssistantError(
                f"Unsupported fridge setting keys: {sorted(unknown_keys)}"
            )

        current = await self.async_fetch_status()
        if as_int(current.get("bodyOffline")):
            raise HomeAssistantError("Fridge body is offline")
        if as_int(current.get("bodyOperating")):
            raise HomeAssistantError("Fridge body is operating locally")

        params = {
            key: updates.get(key, current.get(key, 0))
            for key in FRIDGE_SETTING_PARAMS
        }
        try:
            await self.client.set_device_status(
                self.profile,
                self.usr_id,
                self.device_id,
                self.token,
                params,
            )
        except PanasonicApiAuthError as err:
            raise ConfigEntryAuthFailed("Panasonic Smart China session expired") from err
        except PanasonicApiError as err:
            raise HomeAssistantError(str(err)) from err


async def async_get_fridge_coordinator(
    hass: HomeAssistant,
    entry,
    config: dict[str, Any],
    profile: PanasonicProfile,
    client: PanasonicApiClient,
) -> DataUpdateCoordinator[dict[str, Any]]:
    """Return a shared coordinator for one fridge device under one config entry."""
    runtime = hass.data.setdefault(DOMAIN, {}).setdefault(
        entry.entry_id,
        {"client": PanasonicApiClient(hass, entry.data.get(CONF_SSID))},
    )
    coordinators = runtime.setdefault("fridge_coordinators", {})
    device_id = config[CONF_DEVICE_ID]
    coordinator = coordinators.get(device_id)
    if coordinator:
        if coordinator.data is None:
            await coordinator.async_config_entry_first_refresh()
        return coordinator

    fridge = PanasonicFridgeData(hass, config, profile, client)

    async def _async_update_data() -> dict[str, Any]:
        return await fridge.async_fetch_status()

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"Panasonic Smart China fridge {device_id}",
        update_method=_async_update_data,
        update_interval=POLLING_INTERVAL,
    )
    coordinator.fridge = fridge
    coordinators[device_id] = coordinator
    await coordinator.async_config_entry_first_refresh()
    return coordinator


def as_int(value: Any) -> int | None:
    """Convert Panasonic status values to int when possible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_on_value(value: Any) -> bool | None:
    """Interpret a Panasonic 0/1-like status value."""
    int_value = as_int(value)
    if int_value is None:
        return None
    return int_value != 0


def truncate_nested(value: Any) -> Any:
    """Keep diagnostic attributes reasonably small for Home Assistant state storage."""
    if isinstance(value, dict):
        return {
            str(key): truncate_nested(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [truncate_nested(item) for item in value]
    if isinstance(value, str) and len(value) > MAX_RAW_ATTRIBUTE_CHARS:
        return f"{value[:MAX_RAW_ATTRIBUTE_CHARS]}...<truncated>"
    return value
