"""Tests for the calculation engine, checked against values hand-derived
from the original R script's formulas (see the design spec for the
derivation)."""
import math

import pandas as pd
import pytest

from monoamine_calc.config import load_defaults
from monoamine_calc.engine import (
    EngineError,
    add_ratios,
    build_std_chain,
    compute_concentrations,
    compute_k,
    mean_standard_areas,
    round_and_order,
    run,
)

STD_COLUMNS = ["STD_ID", "MHPG", "NE", "DHBA", "DOPAC", "DA", "5-HIAA", "5-HT"]
SAMPLE_COLUMNS = ["SAMPLE_ID", "MHPG", "NE", "DHBA", "DOPAC", "DA", "5-HIAA", "5-HT", "PROTEIN", "VOLUME"]


@pytest.fixture
def config():
    return load_defaults()


@pytest.fixture
def standards():
    return pd.DataFrame(
        [
            ["S1", 100, 200, 500, 300, 400, 250, 350],
            ["S2", 120, 180, 520, 280, 420, 270, 330],
        ],
        columns=STD_COLUMNS,
    )


@pytest.fixture
def samples():
    return pd.DataFrame(
        [
            ["A1", 90, 210, 480, 310, 390, 240, 360, 1.5, 0.1],
            ["A2", 130, 170, 530, 270, 430, 280, 320, 2.0, 0.1],
        ],
        columns=SAMPLE_COLUMNS,
    )


# ---------------------------------------------------------------------------
# 1. Standard dilution chain
# ---------------------------------------------------------------------------

# analyte: (step_d, corrected_d, step_e, step_f)
EXPECTED_CHAIN = {
    "DOPAC":  (35.5200, 35.520000000, 5.920000000, 0.592000000),
    "DA":     (86.2400, 69.659132891, 11.609855482, 1.160985548),
    "5-HIAA": (67.2000, 67.200000000, 11.200000000, 1.120000000),
    "5-HT":   (188.0000, 140.405732188, 23.400955365, 2.340095536),
    "NE":     (120.3200, 98.986567227, 16.497761204, 1.649776120),
    "MHPG":   (78.2400, 78.240000000, 13.040000000, 1.304000000),
}


def test_std_chain_matches_r_script(config):
    chain = build_std_chain(config)
    by_analyte = chain.set_index("Analyte")
    for analyte, (step_d, corrected_d, step_e, step_f) in EXPECTED_CHAIN.items():
        row = by_analyte.loc[analyte]
        assert row["Step D (ng/ml)"] == pytest.approx(step_d, abs=1e-6)
        assert row["Corrected Step D (ng/ml)"] == pytest.approx(corrected_d, abs=1e-9)
        assert row["Step E (ng/ml)"] == pytest.approx(step_e, abs=1e-9)
        assert row["Step F (ng/ml)"] == pytest.approx(step_f, abs=1e-9)


def test_std_chain_excludes_internal_standard(config):
    chain = build_std_chain(config)
    assert "DHBA" not in chain["Analyte"].values


# ---------------------------------------------------------------------------
# 2. Mean standard areas
# ---------------------------------------------------------------------------

def test_mean_standard_areas(config, standards):
    means = mean_standard_areas(standards, config)
    assert means["DHBA"] == pytest.approx(510.0)
    assert means["MHPG"] == pytest.approx(110.0)
    assert means["5-HT"] == pytest.approx(340.0)


# ---------------------------------------------------------------------------
# 3. K multiplier
# ---------------------------------------------------------------------------

def test_compute_k(config, samples, standards):
    means = mean_standard_areas(standards, config)
    k, warnings = compute_k(samples, means, config)
    assert warnings == []
    assert k["A1"] == pytest.approx(0.070833333, abs=1e-9)
    assert k["A2"] == pytest.approx(0.048113208, abs=1e-9)


def test_compute_k_zero_denominator_warns_instead_of_inf(config):
    standards = pd.DataFrame([["S1", 100, 200, 500, 300, 400, 250, 350]], columns=STD_COLUMNS)
    samples = pd.DataFrame(
        [["A1", 90, 210, 0, 310, 390, 240, 360, 0, 0.1]], columns=SAMPLE_COLUMNS
    )
    means = mean_standard_areas(standards, config)
    k, warnings = compute_k(samples, means, config)
    assert math.isnan(k["A1"])
    assert len(warnings) == 1
    assert "A1" in warnings[0]


def test_compute_k_missing_internal_standard_average_raises(config, samples):
    standards = pd.DataFrame(
        [["S1", 100, 200, None, 300, 400, 250, 350]], columns=STD_COLUMNS
    )
    means = mean_standard_areas(standards, config)
    with pytest.raises(EngineError):
        compute_k(samples, means, config)


# ---------------------------------------------------------------------------
# 5/6. Ratios + rounding
# ---------------------------------------------------------------------------

def test_add_ratios_handles_zero_and_nan_denominator(config):
    wide = pd.DataFrame({
        "SAMPLE_ID": ["A1", "A2", "A3"],
        "MHPG": [1.0, 2.0, 3.0],
        "NE": [2.0, 0.0, float("nan")],
    })
    cfg = config
    cfg.ratio_pairs = [("MHPG", "NE")]
    out = add_ratios(wide, cfg)
    assert out["MHPG/NE"][0] == pytest.approx(0.5)
    assert math.isnan(out["MHPG/NE"][1])
    assert math.isnan(out["MHPG/NE"][2])


def test_round_and_order_applies_output_order(config):
    wide = pd.DataFrame({"NE": [1.23456], "SAMPLE_ID": ["A1"], "MHPG": [2.34567]})
    config.output_order = ["SAMPLE_ID", "MHPG", "NE"]
    config.round_decimals = 2
    out = round_and_order(wide, config)
    assert list(out.columns) == ["SAMPLE_ID", "MHPG", "NE"]
    assert out["MHPG"][0] == pytest.approx(2.35)
    assert out["NE"][0] == pytest.approx(1.23)


# ---------------------------------------------------------------------------
# End-to-end golden fixture
# ---------------------------------------------------------------------------

EXPECTED_WIDE = {
    "A1": {"5-HT": 0.176, "5-HIAA": 0.073, "5-HIAA/5-HT": 0.417, "DA": 0.078, "DOPAC": 0.045,
           "DOPAC/DA": 0.573, "NE": 0.129, "MHPG": 0.076, "MHPG/NE": 0.585},
    "A2": {"5-HT": 0.106, "5-HIAA": 0.058, "5-HIAA/5-HT": 0.548, "DA": 0.059, "DOPAC": 0.027,
           "DOPAC/DA": 0.453, "NE": 0.071, "MHPG": 0.074, "MHPG/NE": 1.044},
}


def test_run_end_to_end_golden_values(config, samples, standards):
    result = run(samples, standards, config)
    assert result.warnings == []

    assert list(result.concentrations.columns) == [
        "SAMPLE_ID", "5-HT", "5-HIAA", "5-HIAA/5-HT", "DA", "DOPAC", "DOPAC/DA", "NE", "MHPG", "MHPG/NE",
    ]

    by_id = result.concentrations.set_index("SAMPLE_ID")
    for sample_id, expected in EXPECTED_WIDE.items():
        for col, value in expected.items():
            assert by_id.loc[sample_id, col] == pytest.approx(value, abs=1e-3), (
                f"{sample_id}.{col}"
            )

    assert result.k_by_sample["A1"] == pytest.approx(0.070833333, abs=1e-9)
    assert result.k_by_sample["A2"] == pytest.approx(0.048113208, abs=1e-9)


def test_mw_correction_toggle_scales_output_exactly(config, samples, standards):
    """Enabling MW correction for MHPG should scale its unrounded
    concentration by exactly the configured MW ratio, and touch no other
    analyte."""
    baseline = run(samples, standards, load_defaults())

    config.analyte("MHPG").apply_mw_correction = True
    corrected = run(samples, standards, config)

    ratio = config.analyte("MHPG").mw_ratio
    base_by_id = baseline.concentrations.set_index("SAMPLE_ID")
    corr_by_id = corrected.concentrations.set_index("SAMPLE_ID")

    for sample_id in ("A1", "A2"):
        assert corr_by_id.loc[sample_id, "MHPG"] == pytest.approx(
            base_by_id.loc[sample_id, "MHPG"] * ratio, abs=2e-3
        )
        for other in ("DA", "5-HT", "NE", "DOPAC", "5-HIAA"):
            assert corr_by_id.loc[sample_id, other] == base_by_id.loc[sample_id, other]
