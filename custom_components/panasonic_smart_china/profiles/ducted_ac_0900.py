"""Verified profile for Panasonic Smart China 0900 ducted AC devices."""

from __future__ import annotations

from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVACMode,
)

from ..models import (
    ENTITY_KIND_DUCTED_AC,
    PLATFORM_CLIMATE,
    PROTOCOL_AC_STATUS,
    PanasonicEndpoint,
    PanasonicProfile,
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

DUCTED_AC_0900_PROFILE = PanasonicProfile(
    profile_id="ducted_ac_0900",
    controller_model="CZ-RD501DW2",
    name="松下风管机线控器 (CZ-RD501DW2)",
    category_ids=frozenset({"0900"}),
    ha_platforms=(PLATFORM_CLIMATE,),
    entity_kind=ENTITY_KIND_DUCTED_AC,
    protocol=PROTOCOL_AC_STATUS,
    status_endpoint=PanasonicEndpoint(
        path="ACDevGetStatusInfoAW",
        request_id=100,
        require_results=True,
        required_result_keys=frozenset({"runStatus"}),
    ),
    set_endpoint=PanasonicEndpoint(
        path="ACDevSetStatusInfoAW",
        request_id=200,
        require_results=False,
    ),
    temp_scale=2,
    default_hvac_mode=HVACMode.COOL,
    hvac_mapping=HVAC_MAPPING,
    fan_mapping=FAN_MAPPING,
    fan_payload_overrides={
        FAN_MUTE: {"windSet": 10, "muteMode": 1},
    },
    safe_status_keys=SAFE_STATUS_KEYS,
)
