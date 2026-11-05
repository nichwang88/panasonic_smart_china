import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .api import PanasonicApiClient
from .const import (
    CONF_CATEGORY, CONF_CONTROLLER_MODEL, CONF_DEVICE_ID, CONF_DEVICES,
    CONF_ENABLED, CONF_PROFILE_ID, CONF_SSID, CONF_USR_ID, DOMAIN,
)
from .fridge import async_get_fridge_coordinator
from .models import ENTITY_KIND_FRIDGE_PROBE
from .profiles import find_profile_for_device_config, supported_platforms

_LOGGER = logging.getLogger(__name__)

PLATFORMS = list(supported_platforms())

def _async_create_account_device(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Register the account service before its appliance entities."""
    account_id = entry.unique_id or entry.data.get(CONF_USR_ID)
    if not account_id:
        return None
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, str(account_id))},
        name=entry.title,
        manufacturer="Panasonic",
        model="Smart China",
        entry_type=dr.DeviceEntryType.SERVICE,
    )
    return device.id

async def async_setup(hass: HomeAssistant, config: dict):
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    account_device_id = _async_create_account_device(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = {
        "client": PanasonicApiClient(hass, entry.data.get(CONF_SSID)),
        "account_device_id": account_device_id,
    }

    # First-refresh failures must retry this entry, not strand one platform.
    for device_id, config in entry.data.get(CONF_DEVICES, {}).items():
        if not config.get(CONF_ENABLED, True):
            continue
        profile = find_profile_for_device_config(
            profile_id=config.get(CONF_PROFILE_ID),
            controller_model=config.get(CONF_CONTROLLER_MODEL),
            category_id=config.get(CONF_CATEGORY),
        )
        if not profile or profile.entity_kind != ENTITY_KIND_FRIDGE_PROBE:
            continue
        await async_get_fridge_coordinator(
            hass, entry, {**entry.data, **config, CONF_DEVICE_ID: device_id},
            profile, hass.data[DOMAIN][entry.entry_id]["client"],
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
