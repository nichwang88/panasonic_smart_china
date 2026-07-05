"""Probe profile for Panasonic Smart China 0100 Fridge-43 devices."""

from __future__ import annotations

from ..models import (
    ENTITY_KIND_FRIDGE_PROBE,
    PLATFORM_BINARY_SENSOR,
    PLATFORM_SENSOR,
    PROTOCOL_FRIDGE_PROBE,
    TOKEN_STRATEGY_DEVICE_ID_SHA512_PRESERVE_SUFFIX,
    PanasonicEndpoint,
    PanasonicProfile,
)

FRIDGE_0100_FRIDGE_43_PROFILE = PanasonicProfile(
    profile_id="fridge_0100_fridge_43",
    controller_model="Fridge-43",
    name="松下冰箱探针 (Fridge-43)",
    category_ids=frozenset({"0100"}),
    model_ids=frozenset({"Fridge-43"}),
    ha_platforms=(PLATFORM_SENSOR, PLATFORM_BINARY_SENSOR),
    entity_kind=ENTITY_KIND_FRIDGE_PROBE,
    protocol=PROTOCOL_FRIDGE_PROBE,
    token_strategy=TOKEN_STRATEGY_DEVICE_ID_SHA512_PRESERVE_SUFFIX,
    status_endpoint=PanasonicEndpoint(
        path="FDevGetStatusInfo",
        request_id=100,
        require_results=True,
    ),
    set_endpoint=PanasonicEndpoint(
        path="",
        request_id=0,
        require_results=False,
    ),
)
