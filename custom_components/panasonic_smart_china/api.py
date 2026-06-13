"""Panasonic Smart China cloud API client."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

BASE_URL = "https://app.psmartcloud.com/App"
URL_LOGIN = f"{BASE_URL}/UsrLogin"
URL_GET_DEV = f"{BASE_URL}/UsrGetBindDevInfo"
URL_GET_TOKEN = f"{BASE_URL}/UsrGetToken"
URL_GET_AC_STATUS = f"{BASE_URL}/ACDevGetStatusInfoAW"
URL_SET_AC_STATUS = f"{BASE_URL}/ACDevSetStatusInfoAW"

AUTH_ERROR_CODES = {"3003", "3004"}
SUCCESS_ERROR_CODES = {None, "", 0, "0", "0000"}


class PanasonicApiError(Exception):
    """Base exception for Panasonic cloud API failures."""


class PanasonicApiAuthError(PanasonicApiError):
    """Raised when the Panasonic session is expired or invalid."""


class PanasonicApiResponseError(PanasonicApiError):
    """Raised when the Panasonic cloud returns an invalid response."""


@dataclass(frozen=True)
class LoginResult:
    """Successful login result."""

    usr_id: str
    ssid: str
    family_id: str
    real_family_id: str
    devices: dict[str, dict[str, Any]]


class PanasonicApiClient:
    """Small async client for the reverse engineered Panasonic cloud API."""

    def __init__(self, hass: HomeAssistant, ssid: str | None = None) -> None:
        self._hass = hass
        self.ssid = ssid

    async def authenticate(self, username: str, password: str) -> LoginResult:
        """Run the full login flow and return the account devices."""
        token_res = await self._post(
            URL_GET_TOKEN,
            {
                "id": 1,
                "uiVersion": 4.0,
                "params": {"usrId": username},
            },
            headers=self._app_headers(),
            require_results=True,
        )
        token_start = token_res["results"].get("token")
        if not token_start:
            raise PanasonicApiResponseError("GetToken response did not include token")

        pwd_md5 = hashlib.md5(password.encode()).hexdigest().upper()
        inter_md5 = hashlib.md5(f"{pwd_md5}{username}".encode()).hexdigest().upper()
        final_token = hashlib.md5(f"{inter_md5}{token_start}".encode()).hexdigest().upper()

        login_res = await self._post(
            URL_LOGIN,
            {
                "id": 2,
                "uiVersion": 4.0,
                "params": {
                    "telId": "00:00:00:00:00:00",
                    "checkFailCount": 0,
                    "usrId": username,
                    "pwd": final_token,
                },
            },
            headers=self._app_headers(),
            require_results=True,
        )
        results = login_res["results"]
        usr_id = results["usrId"]
        ssid = results["ssId"]
        family_id = results["familyId"]
        real_family_id = results["realFamilyId"]

        self.ssid = ssid
        devices = await self.get_devices(usr_id, family_id, real_family_id)
        return LoginResult(
            usr_id=usr_id,
            ssid=ssid,
            family_id=family_id,
            real_family_id=real_family_id,
            devices=devices,
        )

    async def get_devices(
        self, usr_id: str, family_id: str, real_family_id: str
    ) -> dict[str, dict[str, Any]]:
        """Return all bound devices for the current account session."""
        res = await self._post(
            URL_GET_DEV,
            {
                "id": 3,
                "uiVersion": 4.0,
                "params": {
                    "realFamilyId": real_family_id,
                    "familyId": family_id,
                    "usrId": usr_id,
                },
            },
            headers=self._app_headers(include_cookie=True),
            require_results=True,
        )

        devices = {}
        for dev in res["results"].get("devList", []):
            device_id = dev.get("deviceId")
            params = dev.get("params")
            if device_id and isinstance(params, dict):
                devices[device_id] = params
        return devices

    async def get_ac_status(self, usr_id: str, device_id: str, token: str) -> dict[str, Any]:
        """Fetch the latest status for a 0900 ducted AC device."""
        res = await self._post(
            URL_GET_AC_STATUS,
            {
                "id": 100,
                "usrId": usr_id,
                "deviceId": device_id,
                "token": token,
            },
            headers=self._control_headers(),
            require_results=True,
        )

        results = res["results"]
        if not isinstance(results, dict):
            raise PanasonicApiResponseError("Status response results must be an object")
        if "runStatus" not in results:
            raise PanasonicApiResponseError("Status response did not include runStatus")
        return results

    async def set_ac_status(
        self, usr_id: str, device_id: str, token: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Set the latest status for a 0900 ducted AC device."""
        return await self._post(
            URL_SET_AC_STATUS,
            {
                "id": 200,
                "usrId": usr_id,
                "deviceId": device_id,
                "token": token,
                "params": params,
            },
            headers=self._control_headers(),
            require_results=False,
        )

    async def _post(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
        require_results: bool,
    ) -> dict[str, Any]:
        session = async_get_clientsession(self._hass)
        try:
            async with async_timeout.timeout(10):
                response = await session.post(url, json=payload, headers=headers, ssl=False)
                if response.status != 200:
                    text = await response.text()
                    raise PanasonicApiResponseError(
                        f"HTTP {response.status} from {url}: {text[:200]}"
                    )

                try:
                    data = await response.json()
                except Exception as err:
                    text = await response.text()
                    raise PanasonicApiResponseError(
                        f"Invalid JSON from {url}: {text[:200]}"
                    ) from err
        except PanasonicApiError:
            raise
        except TimeoutError as err:
            raise PanasonicApiResponseError(f"Request timed out: {url}") from err
        except Exception as err:
            raise PanasonicApiResponseError(f"Request failed: {url}: {err}") from err

        if not isinstance(data, dict):
            raise PanasonicApiResponseError(f"Unexpected JSON response from {url}")

        self._raise_for_business_error(data)
        if require_results and "results" not in data:
            raise PanasonicApiResponseError(f"Missing results in response from {url}")
        return data

    def _raise_for_business_error(self, data: dict[str, Any]) -> None:
        error_code = data.get("errorCode")
        if error_code in SUCCESS_ERROR_CODES:
            return

        error_code_text = str(error_code)
        message = data.get("errorMessage") or data.get("msg") or "Panasonic API error"
        if error_code_text in AUTH_ERROR_CODES:
            raise PanasonicApiAuthError(f"{message} (errorCode: {error_code_text})")
        raise PanasonicApiResponseError(f"{message} (errorCode: {error_code_text})")

    def _app_headers(self, include_cookie: bool = False) -> dict[str, str]:
        headers = {
            "User-Agent": "SmartApp",
            "Content-Type": "application/json",
        }
        if include_cookie and self.ssid:
            headers["Cookie"] = f"SSID={self.ssid}"
        return headers

    def _control_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X)",
            "xtoken": f"SSID={self.ssid}",
            "DNT": "1",
            "Origin": "https://app.psmartcloud.com",
            "X-Requested-With": "XMLHttpRequest",
        }
