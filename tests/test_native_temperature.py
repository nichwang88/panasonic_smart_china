"""The integration must import without HA's legacy-temperature migration."""

import subprocess
import sys


def test_climate_import_uses_supported_temperature_api():
    result = subprocess.run(
        [sys.executable, "-c", "import custom_components.panasonic_smart_china.climate"],
        capture_output=True, text=True, check=True,
    )
    assert "provides the deprecated" not in result.stderr
