"""Pure calculation engine, ported from "monoamine calculation program.R".

No file I/O, no clipboard, no GUI imports here -- this module only takes
pandas DataFrames and a Config and returns DataFrames. That makes it
directly unit-testable and reusable from a script, a notebook, or a
different front-end.

Pipeline (mirrors the R script section by section):

1. build_std_chain(config)          -> the A..F dilution-chain table
2. mean_standard_areas(standards)   -> per-analyte mean peak area
3. compute_k(samples, mean_areas, config)          -> per-sample multiplier K
4. compute_concentrations(samples, std_chain, mean_areas, config)
5. add_ratios(wide, config)
6. round_and_order(wide, config)

run() chains all of the above and also returns a list of human-readable
warnings (e.g. division-by-zero cases) instead of silently emitting Inf,
which is what the R script does.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import Config, normalize_analyte_name


class EngineError(ValueError):
    """Raised for conditions that should stop the calculation (mirrors the
    R script's `stop(...)` calls)."""


@dataclass
class CalculationResult:
    concentrations: pd.DataFrame   # wide, final, rounded, ordered
    std_chain: pd.DataFrame        # the A..F table, for the Results preview / Excel sheet
    mean_standard_areas: pd.Series # per-analyte mean peak area, indexed by analyte name
    k_by_sample: pd.Series         # per-sample K, indexed by SAMPLE_ID
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 1. Standard dilution chain (A -> F)
# ---------------------------------------------------------------------------

def build_std_chain(config: Config) -> pd.DataFrame:
    """Reproduces the STD_calc table: for every non-internal-standard analyte,
    walk weight (mg) through steps A-F, applying the per-analyte MW
    correction (if enabled) between D and E."""
    d = config.dilution
    rows = []
    for a in config.analytes:
        if a.is_internal_standard:
            continue
        if a.standard_weight_mg is None:
            raise EngineError(f"{a.name}: no standard weight configured")
        step_a = a.standard_weight_mg / d.step_a_divisor
        step_b = step_a * d.step_b_multiplier
        step_c = step_b * d.step_c_multiplier
        step_d = step_c / d.step_d_divisor
        if a.apply_mw_correction:
            if a.mw_ratio is None:
                raise EngineError(f"{a.name}: MW correction enabled but no ratio set")
            corrected_d = step_d * a.mw_ratio
        else:
            corrected_d = step_d
        step_e = corrected_d / d.step_e_divisor
        step_f = step_e / d.step_f_divisor
        rows.append({
            "Analyte": a.name,
            "Weight mg": a.standard_weight_mg,
            "Step A (mg/ml)": step_a,
            "Step B (ng/ml)": step_b,
            "Step C (ng/ml)": step_c,
            "Step D (ng/ml)": step_d,
            "Corrected Step D (ng/ml)": corrected_d,
            "Step E (ng/ml)": step_e,
            "Step F (ng/ml)": step_f,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. Mean standard peak areas
# ---------------------------------------------------------------------------

def mean_standard_areas(standards: pd.DataFrame, config: Config) -> pd.Series:
    """Per-analyte mean peak area across all standard rows (NaNs ignored,
    matching R's na.rm = TRUE). Index is analyte name as in `standards`
    columns (excludes STD_ID)."""
    analyte_cols = [c for c in standards.columns if c != "STD_ID"]
    numeric = standards[analyte_cols].apply(pd.to_numeric, errors="coerce")
    return numeric.mean(axis=0, skipna=True)


# ---------------------------------------------------------------------------
# 3. Per-sample multiplier K
# ---------------------------------------------------------------------------

def compute_k(samples: pd.DataFrame, mean_areas: pd.Series, config: Config) -> tuple[pd.Series, list[str]]:
    """K = (mean_std_area[internal_standard] * VOLUME) / (sample_area[internal_standard] * PROTEIN)

    Returns (K indexed by SAMPLE_ID, warnings for rows with a zero
    denominator -- the R script would silently produce Inf there)."""
    internal = config.internal_standard_spec()
    key = normalize_analyte_name(internal.name)
    match = _find_column(mean_areas.index, key)
    if match is None:
        raise EngineError(f"Could not find internal standard '{internal.name}' in standards data")
    std_avg_internal = mean_areas[match]
    if pd.isna(std_avg_internal):
        raise EngineError(
            f"Could not obtain a single, non-NA standard average for {internal.name}."
        )

    sample_internal_col = _find_column(samples.columns, key)
    if sample_internal_col is None:
        raise EngineError(f"Could not find internal standard '{internal.name}' in samples data")

    warnings: list[str] = []
    denom = samples[sample_internal_col] * samples["PROTEIN"]
    zero_mask = (denom == 0) | denom.isna()

    # Compute K positionally (numpy arrays, not pandas alignment) and only
    # then attach the SAMPLE_ID index -- avoids index-alignment surprises
    # between differently-indexed Series.
    with np.errstate(divide="ignore", invalid="ignore"):
        k_values = (std_avg_internal * samples["VOLUME"].to_numpy(dtype=float)) / denom.to_numpy(dtype=float)
    k_values = pd.Series(k_values).mask(zero_mask.to_numpy(), other=np.nan)
    k = pd.Series(k_values.to_numpy(), index=samples["SAMPLE_ID"].to_numpy())

    for sample_id, is_zero in zip(samples["SAMPLE_ID"], zero_mask):
        if is_zero:
            warnings.append(
                f"Sample {sample_id}: {internal.name} area or PROTEIN is zero/missing -- "
                "K could not be computed (shown as blank, not Infinity)."
            )
    return k, warnings


def _find_column(columns, normalized_key: str) -> str | None:
    for c in columns:
        if normalize_analyte_name(str(c)) == normalized_key:
            return c
    return None


# ---------------------------------------------------------------------------
# 4. Concentrations
# ---------------------------------------------------------------------------

def compute_concentrations(
    samples: pd.DataFrame,
    std_chain: pd.DataFrame,
    mean_areas: pd.Series,
    config: Config,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """concentration[analyte] = K * sample_area[analyte] * (std_conc[analyte] / mean_std_area[analyte])

    where std_conc comes from std_chain's Step E or Step F column, chosen by
    config.std_step. Returns (wide concentrations DataFrame indexed by
    SAMPLE_ID, K series, warnings)."""
    k, k_warnings = compute_k(samples, mean_areas, config)
    warnings = list(k_warnings)

    step_col = "Step E (ng/ml)" if config.std_step.upper() == "E" else "Step F (ng/ml)"
    out_analytes = config.output_analytes()

    data = {"SAMPLE_ID": samples["SAMPLE_ID"]}
    for analyte in out_analytes:
        key = normalize_analyte_name(analyte)

        chain_row = std_chain[std_chain["Analyte"].apply(
            lambda x: normalize_analyte_name(x) == key
        )]
        if chain_row.empty:
            raise EngineError(f"No standard dilution chain entry for analyte: {analyte}")
        std_conc = float(chain_row.iloc[0][step_col])

        mean_col = _find_column(mean_areas.index, key)
        if mean_col is None:
            raise EngineError(f"No standard peak-area data for analyte: {analyte}")
        mean_area = mean_areas[mean_col]

        sample_col = _find_column(samples.columns, key)
        if sample_col is None:
            raise EngineError(f"No sample peak-area data for analyte: {analyte}")

        if pd.isna(mean_area) or mean_area == 0:
            warnings.append(
                f"Analyte {analyte}: mean standard area is zero/missing -- "
                "concentration could not be computed for any sample."
            )
            conc = pd.Series(np.nan, index=samples.index)
        else:
            ratio = std_conc / mean_area
            conc = k.values * samples[sample_col].to_numpy(dtype=float) * ratio

        data[analyte] = conc

    wide = pd.DataFrame(data)
    return wide, k, warnings


# ---------------------------------------------------------------------------
# 5. Ratios
# ---------------------------------------------------------------------------

def add_ratios(wide: pd.DataFrame, config: Config) -> pd.DataFrame:
    wide = wide.copy()
    for numerator, denominator in config.ratio_pairs:
        col_name = f"{numerator}/{denominator}"
        if numerator not in wide.columns or denominator not in wide.columns:
            continue
        num = wide[numerator]
        den = wide[denominator]
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = num / den
        ratio = ratio.mask(num.isna() | den.isna() | (den == 0))
        wide[col_name] = ratio
    return wide


# ---------------------------------------------------------------------------
# 6. Rounding + final column order
# ---------------------------------------------------------------------------

def round_and_order(wide: pd.DataFrame, config: Config) -> pd.DataFrame:
    wide = wide.copy()
    numeric_cols = [c for c in wide.columns if c != "SAMPLE_ID"]
    wide[numeric_cols] = wide[numeric_cols].round(config.round_decimals)

    ordered_cols = [c for c in config.output_order if c in wide.columns]
    remaining = [c for c in wide.columns if c not in ordered_cols]
    return wide[ordered_cols + remaining]


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------

def run(samples: pd.DataFrame, standards: pd.DataFrame, config: Config) -> CalculationResult:
    config.validate()

    std_chain = build_std_chain(config)
    mean_areas = mean_standard_areas(standards, config)
    wide, k, warnings = compute_concentrations(samples, std_chain, mean_areas, config)
    wide = add_ratios(wide, config)
    wide = round_and_order(wide, config)

    return CalculationResult(
        concentrations=wide,
        std_chain=std_chain,
        mean_standard_areas=mean_areas,
        k_by_sample=k,
        warnings=warnings,
    )
