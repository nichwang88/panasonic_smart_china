"""Device profile registry."""

from __future__ import annotations

from .ducted_ac_0900 import DUCTED_AC_0900_PROFILE

SUPPORTED_PROFILES = {
    "ducted_ac_0900": DUCTED_AC_0900_PROFILE,
}


def find_profiles_for_category(category_id: str | None) -> dict[str, dict]:
    """Find verified profiles for a Panasonic category id."""
    if not category_id:
        return {}
    return {
        key: profile
        for key, profile in SUPPORTED_PROFILES.items()
        if category_id in profile.get("category_ids", [])
    }
