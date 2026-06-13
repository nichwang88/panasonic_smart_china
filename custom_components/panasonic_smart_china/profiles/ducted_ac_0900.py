"""Verified profile for Panasonic Smart China 0900 ducted AC devices."""

from __future__ import annotations

from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVACMode,
)

FAN_MIN = "Min"
FAN_MAX = "Max"
FAN_MUTE = "Quiet"

SAFE_STATUS_KEYS = {
    "runMode",
    "forceRunning",
    "runStatus",
    "remoteForbidMode",
    "remoteMode",
    "setTemperature",
    "setHumidity",
    "windSet",
    "exchangeWindSet",
    "portraitWindSet",
    "orientationWindSet",
    "nanoeG",
    "nanoe",
    "ecoMode",
    "muteMode",
    "filterReset",
    "powerful",
    "powerfulMode",
    "thermoMode",
    "buzzer",
    "autoRunMode",
    "unusualPresent",
    "runForbidden",
    "inhaleTemperature",
    "outsideTemperature",
    "insideHumidity",
    "alarmCode",
    "nanoeModule",
    "TDWindModule",
}

HVAC_MAPPING = {
    HVACMode.COOL: 3,
    HVACMode.HEAT: 4,
    HVACMode.DRY: 2,
    HVACMode.AUTO: 0,
}

FAN_MAPPING = {
    FAN_AUTO: 10,
    FAN_MIN: 3,
    FAN_LOW: 4,
    FAN_MEDIUM: 5,
    FAN_HIGH: 6,
    FAN_MAX: 7,
}

DUCTED_AC_0900_PROFILE = {
    "name": "松下风管机线控器 (CZ-RD501DW2)",
    "device_type": "AC",
    "category_ids": ["0900"],
    "temp_scale": 2,
    "default_hvac_mode": HVACMode.COOL,
    "hvac_mapping": HVAC_MAPPING,
    "fan_mapping": FAN_MAPPING,
    "fan_payload_overrides": {
        FAN_MUTE: {"windSet": 10, "muteMode": 1},
    },
    "safe_status_keys": SAFE_STATUS_KEYS,
}
