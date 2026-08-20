"""Tests for the editable-constants layer: load/save round-trips, presets,
and reset-to-defaults."""
import pytest

from monoamine_calc.config import (
    Config,
    ConfigError,
    load_defaults,
    load_active_or_defaults,
    list_presets,
    load_preset,
    save_active,
    save_preset,
    delete_preset,
    export_preset,
    import_preset,
    reset_to_defaults,
)


def test_defaults_load_and_validate():
    cfg = load_defaults()
    cfg.validate()
    assert cfg.internal_standard == "DHBA"
    assert cfg.std_step == "F"
    names = {a.name for a in cfg.analytes}
    assert names == {"MHPG", "NE", "DHBA", "DOPAC", "DA", "5-HIAA", "5-HT"}


def test_defaults_match_r_script_values():
    cfg = load_defaults()
    assert cfg.analyte("DA").standard_weight_mg == pytest.approx(10.78)
    assert cfg.analyte("DA").mw_ratio == pytest.approx(0.807735771)
    assert cfg.analyte("DA").apply_mw_correction is True
    assert cfg.analyte("MHPG").apply_mw_correction is False
    assert cfg.analyte("DOPAC").mw_ratio is None
    assert cfg.internal_standard_spec().name == "DHBA"


def test_normalized_analyte_lookup_ignores_punctuation():
    cfg = load_defaults()
    assert cfg.analyte("5HT").name == "5-HT"
    assert cfg.analyte("5-hiaa").name == "5-HIAA"


def test_round_trip_to_dict_and_back(tmp_path):
    cfg = load_defaults()
    path = tmp_path / "config.json"
    cfg.save(path)
    reloaded = Config.load(path)
    assert reloaded.to_dict() == cfg.to_dict()


def test_validate_rejects_missing_internal_standard():
    cfg = load_defaults()
    for a in cfg.analytes:
        a.is_internal_standard = False
    with pytest.raises(ConfigError):
        cfg.validate()


def test_validate_rejects_two_internal_standards():
    cfg = load_defaults()
    cfg.analyte("NE").is_internal_standard = True  # DHBA is already one
    with pytest.raises(ConfigError):
        cfg.validate()


def test_validate_rejects_correction_without_ratio():
    cfg = load_defaults()
    cfg.analyte("DOPAC").apply_mw_correction = True  # DOPAC has no mw_ratio
    with pytest.raises(ConfigError):
        cfg.validate()


def test_preset_save_load_delete(monkeypatch, tmp_path):
    monkeypatch.setattr("monoamine_calc.config.PRESETS_DIR", tmp_path / "presets")
    cfg = load_defaults()
    cfg.analyte("MHPG").standard_weight_mg = 12.34

    save_preset("test batch", cfg)
    assert "test batch" in list_presets()

    reloaded = load_preset("test batch")
    assert reloaded.analyte("MHPG").standard_weight_mg == pytest.approx(12.34)

    delete_preset("test batch")
    assert "test batch" not in list_presets()


def test_preset_name_validation(monkeypatch, tmp_path):
    monkeypatch.setattr("monoamine_calc.config.PRESETS_DIR", tmp_path / "presets")
    cfg = load_defaults()
    with pytest.raises(ConfigError):
        save_preset("../escape", cfg)
    with pytest.raises(ConfigError):
        save_preset("", cfg)


def test_export_import_preset_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr("monoamine_calc.config.PRESETS_DIR", tmp_path / "presets")
    cfg = load_defaults()
    cfg.analyte("DA").mw_ratio = 0.5
    dest = tmp_path / "shared_constants.json"
    export_preset(cfg, dest)

    imported = import_preset(dest, "shared")
    assert imported.analyte("DA").mw_ratio == pytest.approx(0.5)
    assert "shared" in list_presets()


def test_load_active_or_defaults_falls_back_when_no_active_config(monkeypatch, tmp_path):
    monkeypatch.setattr("monoamine_calc.config.ACTIVE_CONFIG_PATH", tmp_path / "config.json")
    cfg = load_active_or_defaults()
    assert cfg.to_dict() == load_defaults().to_dict()


def test_save_active_then_load_active_or_defaults_round_trips(monkeypatch, tmp_path):
    monkeypatch.setattr("monoamine_calc.config.ACTIVE_CONFIG_PATH", tmp_path / "config.json")
    cfg = load_defaults()
    cfg.analyte("NE").standard_weight_mg = 99.9
    save_active(cfg)

    reloaded = load_active_or_defaults()
    assert reloaded.analyte("NE").standard_weight_mg == pytest.approx(99.9)


def test_reset_to_defaults_overwrites_active_config(monkeypatch, tmp_path):
    monkeypatch.setattr("monoamine_calc.config.ACTIVE_CONFIG_PATH", tmp_path / "config.json")
    cfg = load_defaults()
    cfg.analyte("NE").standard_weight_mg = 99.9
    save_active(cfg)
    assert load_active_or_defaults().analyte("NE").standard_weight_mg == pytest.approx(99.9)

    restored = reset_to_defaults()
    assert restored.analyte("NE").standard_weight_mg == pytest.approx(15.04)
    assert load_active_or_defaults().analyte("NE").standard_weight_mg == pytest.approx(15.04)
