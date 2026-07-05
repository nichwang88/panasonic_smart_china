"""Device token helpers for Panasonic Smart China."""

from __future__ import annotations

import hashlib

from .models import (
    TOKEN_STRATEGY_DEVICE_ID_SHA512,
    TOKEN_STRATEGY_DEVICE_ID_SHA512_PRESERVE_SUFFIX,
)


class DeviceTokenError(ValueError):
    """Raised when a Panasonic device token cannot be generated."""


def generate_device_token(
    device_id: str,
    strategy: str = TOKEN_STRATEGY_DEVICE_ID_SHA512,
) -> str:
    """Generate the device control token from a Panasonic device id."""
    normalized_device_id = device_id.upper()
    parts = normalized_device_id.split("_", 2)
    if len(parts) < 3:
        raise DeviceTokenError(
            f"Invalid deviceId format: {device_id} (expected MAC_CATEGORY_SUFFIX)"
        )

    mac_part, category, suffix = parts
    if strategy == TOKEN_STRATEGY_DEVICE_ID_SHA512_PRESERVE_SUFFIX:
        original_parts = device_id.split("_", 2)
        suffix = original_parts[2]
    elif strategy != TOKEN_STRATEGY_DEVICE_ID_SHA512:
        raise DeviceTokenError(f"Unsupported token strategy: {strategy}")

    if len(mac_part) < 6:
        raise DeviceTokenError(f"Invalid MAC part in deviceId: {device_id}")

    stoken = f"{mac_part[6:]}_{category}_{mac_part[:6]}"
    inner = hashlib.sha512(stoken.encode()).hexdigest()
    return hashlib.sha512(f"{inner}_{suffix}".encode()).hexdigest()
