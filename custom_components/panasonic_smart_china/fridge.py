"""Shared polling and validated control for Panasonic Fridge-43 devices."""

from __future__ import annotations

import asyncio
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
COMMAND_CONFIRM_ATTEMPTS = 3
COMMAND_CONFIRM_DELAY = 1
TEMPERATURE_LIMITS = {"PCTempSet": (2, 7), "SCS1TempSet": (-3, 7), "FCTempSet": (-23, -17)}
FEATURE_KEYS = frozenset({
    "quickFreeze", "autoIcing", "freshFrozen", "nanoe",
    "SCS1DryStore", "PCMicroFreeze", "PCMilkStore",
})
WRITABLE_KEYS = frozenset(TEMPERATURE_LIMITS) | FEATURE_KEYS
REQUIRED_CONTROL_KEYS = WRITABLE_KEYS | {"bodyOffline", "bodyOperating"}
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
        account_device_id: str | None = None,
    ) -> None:
        self.hass = hass
        self.profile = profile
        self.client = client
        self.account_device_id = account_device_id
        self._command_lock = asyncio.Lock()
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
        info = DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=self.device_name,
            manufacturer="Panasonic",
            model=self.model,
        )
        if self.account_device_id:
            info["via_device_id"] = self.account_device_id
        return info

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

    async def async_set_status(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Serialize read/validate/write/confirm transactions for this device."""
        unknown_keys = set(updates) - WRITABLE_KEYS
        if unknown_keys:
            raise HomeAssistantError(
                f"Unsupported fridge setting keys: {sorted(unknown_keys)}"
            )

        if not updates:
            raise HomeAssistantError("No fridge settings supplied")
        changes = {}
        for key, value in updates.items():
            limits = TEMPERATURE_LIMITS.get(key, (0, 1))
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not limits[0] <= value <= limits[1]
                or value != int(value)
            ):
                raise HomeAssistantError(f"Invalid fridge setting: {key}")
            changes[key] = int(value)
        if changes.get("PCMicroFreeze") == 1 and changes.get("PCMilkStore") == 1:
            raise HomeAssistantError("Microfreeze and milk storage are mutually exclusive")
        if changes.get("PCMicroFreeze") == 1:
            changes["PCMilkStore"] = 0
        elif changes.get("PCMilkStore") == 1:
            changes["PCMicroFreeze"] = 0

        async with self._command_lock:
            current = await self.async_fetch_status()
            validate_control_status(current)
            if as_int(current["bodyOffline"]):
                raise HomeAssistantError("Fridge body is offline")
            if as_int(current["bodyOperating"]):
                raise HomeAssistantError("Fridge body is operating locally")
            effective_nanoe = changes.get("nanoe", as_int(current["nanoe"]))
            effective_temperature = changes.get("SCS1TempSet", as_int(current["SCS1TempSet"]))
            if effective_nanoe == 1 and effective_temperature <= 0:
                raise HomeAssistantError("Nanoe can only be enabled above 0℃")

            # Preserve reported protocol fields. Absent optional compartments
            # are omitted rather than inventing a zero-valued setting.
            params = {key: current[key] for key in FRIDGE_SETTING_PARAMS if key in current}
            params.update(changes)
            try:
                await self.client.set_device_status(
                    self.profile, self.usr_id, self.device_id, self.token, params
                )
            except PanasonicApiAuthError as err:
                raise ConfigEntryAuthFailed("Panasonic Smart China session expired") from err
            except PanasonicApiError as err:
                raise HomeAssistantError(str(err)) from err

            # Readback only: never resend a potentially accepted command.
            for attempt in range(COMMAND_CONFIRM_ATTEMPTS):
                if attempt:
                    await asyncio.sleep(COMMAND_CONFIRM_DELAY)
                confirmed = await self.async_fetch_status()
                validate_control_status(confirmed)
                if (
                    not as_int(confirmed["bodyOffline"])
                    and all(as_int(confirmed.get(key)) == value for key, value in changes.items())
                ):
                    return confirmed
            raise HomeAssistantError("Could not confirm fridge command; refresh device state before retrying")

    async def async_poll_status(self) -> dict[str, Any]:
        """Keep background polling outside an active command transaction."""
        async with self._command_lock:
            return await self.async_fetch_status()


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

    fridge = PanasonicFridgeData(hass, config, profile, client, runtime.get("account_device_id"))

    async def _async_update_data() -> dict[str, Any]:
        return await fridge.async_poll_status()

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"Panasonic Smart China fridge {device_id}",
        update_method=_async_update_data,
        update_interval=POLLING_INTERVAL,
        always_update=False,
    )
    coordinator.fridge = fridge
    coordinators[device_id] = coordinator
    await coordinator.async_config_entry_first_refresh()
    return coordinator


def validate_control_status(data: dict[str, Any]) -> None:
    """Require known control and guard fields before using a cloud snapshot."""
    missing = REQUIRED_CONTROL_KEYS - data.keys()
    if missing:
        raise HomeAssistantError(f"Incomplete fridge status: {sorted(missing)}")
    for key in REQUIRED_CONTROL_KEYS:
        value = data[key]
        try:
            integer = int(value)
        except (TypeError, ValueError, OverflowError) as err:
            raise HomeAssistantError(f"Invalid fridge status field: {key}") from err
        limits = TEMPERATURE_LIMITS.get(key, (0, 1))
        if (
            (isinstance(value, float) and value != integer)
            or not limits[0] <= integer <= limits[1]
        ):
            raise HomeAssistantError(f"Invalid fridge status field: {key}")


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
