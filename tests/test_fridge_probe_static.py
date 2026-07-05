from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "custom_components" / "panasonic_smart_china"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fridge_probe_release_metadata_is_bumped():
    assert '"version": "2.1.1"' in read(DOMAIN / "manifest.json")


def test_fridge_probe_profile_is_registered():
    registry = read(DOMAIN / "profiles" / "__init__.py")
    assert "FRIDGE_0100_FRIDGE_43_PROFILE" in registry
    assert "fridge_0100_fridge_43" in read(
        DOMAIN / "profiles" / "fridge_0100_fridge_43.py"
    )


def test_fridge_probe_platform_is_sensor_only():
    models = read(DOMAIN / "models.py")
    assert 'PLATFORM_SENSOR = "sensor"' in models
    assert 'ENTITY_KIND_FRIDGE_PROBE = "fridge_probe"' in models
    assert (DOMAIN / "sensor.py").exists()


def test_fridge_probe_matches_category_and_model():
    profile = read(DOMAIN / "profiles" / "fridge_0100_fridge_43.py")
    assert 'category_ids=frozenset({"0100"})' in profile
    assert 'model_ids=frozenset({"Fridge-43"})' in profile
