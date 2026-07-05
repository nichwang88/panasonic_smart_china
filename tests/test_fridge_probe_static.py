from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "custom_components" / "panasonic_smart_china"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fridge_probe_release_metadata_is_bumped():
    assert '"version": "2.2.0"' in read(DOMAIN / "manifest.json")
    assert '"name": "Panasonic Smart China"' in read(ROOT / "hacs.json")


def test_fridge_probe_profile_is_registered():
    registry = read(DOMAIN / "profiles" / "__init__.py")
    assert "FRIDGE_0100_FRIDGE_43_PROFILE" in registry
    assert "fridge_0100_fridge_43" in read(
        DOMAIN / "profiles" / "fridge_0100_fridge_43.py"
    )


def test_fridge_probe_platform_is_sensor_only():
    models = read(DOMAIN / "models.py")
    assert 'PLATFORM_SENSOR = "sensor"' in models
    assert 'PLATFORM_BINARY_SENSOR = "binary_sensor"' in models
    assert 'ENTITY_KIND_FRIDGE_PROBE = "fridge_probe"' in models
    assert (DOMAIN / "sensor.py").exists()
    assert (DOMAIN / "binary_sensor.py").exists()


def test_fridge_probe_matches_category_and_model():
    profile = read(DOMAIN / "profiles" / "fridge_0100_fridge_43.py")
    assert 'category_ids=frozenset({"0100"})' in profile
    assert 'model_ids=frozenset({"Fridge-43"})' in profile
    assert 'path="FDevGetStatusInfo"' in profile
    assert "TOKEN_STRATEGY_DEVICE_ID_SHA512_PRESERVE_SUFFIX" in profile
    assert "PLATFORM_BINARY_SENSOR" in profile


def test_fridge_probe_recomputes_token_from_profile_strategy():
    fridge = read(DOMAIN / "fridge.py")
    assert "generate_device_token(self.device_id, profile.token_strategy)" in fridge


def test_fridge_read_only_entities_are_declared():
    sensor = read(DOMAIN / "sensor.py")
    binary_sensor = read(DOMAIN / "binary_sensor.py")
    assert "PCTempCur" in sensor
    assert "FCTempCur" in sensor
    assert "SCS1TempCur" in sensor
    assert "PCGate1" in binary_sensor
    assert "FCGate1" in binary_sensor
    assert "waterLack" in binary_sensor
    assert "async_get_fridge_coordinator" in sensor
    assert "async_get_fridge_coordinator" in binary_sensor
