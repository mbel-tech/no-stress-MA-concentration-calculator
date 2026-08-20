"""Editable-constants layer for the monoamine concentration calculator.

Every fixed number that used to be hard-coded mid-script in
"monoamine calculation program.R" lives here as data, not code:
- per-analyte standard weights and molecular-weight ratios
- the six-step dilution-chain constants (A -> F)
- rounding, output order, ratio pairs, decimal separator

`defaults.json` (shipped with the app, next to this file) holds the exact
values from the R script and is never written to. User edits are saved to
`~/.no-stress-ma/config.json` (the "active" config, auto-loaded on next
launch) and to named presets under `~/.no-stress-ma/presets/<name>.json`.
"Reset to defaults" restores `defaults.json` without touching saved presets.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULTS_PATH = PACKAGE_DIR / "defaults.json"

USER_DIR = Path.home() / ".no-stress-ma"
ACTIVE_CONFIG_PATH = USER_DIR / "config.json"
PRESETS_DIR = USER_DIR / "presets"


class ConfigError(ValueError):
    """Raised when a config file is structurally invalid."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class AnalyteSpec:
    name: str
    standard_weight_mg: float | None = None   # None for the internal standard
    mw_ratio: float | None = None              # None if no ratio is defined
    apply_mw_correction: bool = False
    formula: str | None = None
    is_internal_standard: bool = False

    def normalized_key(self) -> str:
        """Punctuation/case-insensitive key, e.g. '5-HT' and '5HT' match."""
        return normalize_analyte_name(self.name)


@dataclass
class DilutionChain:
    step_a_divisor: float = 10.0
    step_b_multiplier: float = 20000.0
    step_c_multiplier: float = 0.02
    step_d_divisor: float = 5.0
    step_e_divisor: float = 6.0
    step_f_divisor: float = 10.0


@dataclass
class Config:
    analytes: list[AnalyteSpec] = field(default_factory=list)
    dilution: DilutionChain = field(default_factory=DilutionChain)
    internal_standard: str = "DHBA"
    std_step: str = "F"                       # "E" or "F"
    round_decimals: int = 3
    ratio_pairs: list[tuple[str, str]] = field(default_factory=list)
    output_order: list[str] = field(default_factory=list)
    decimal_separator: str = "."

    # -- lookups -----------------------------------------------------------

    def analyte(self, name: str) -> AnalyteSpec:
        key = normalize_analyte_name(name)
        for a in self.analytes:
            if a.normalized_key() == key:
                return a
        raise ConfigError(f"Unknown analyte: {name}")

    def has_analyte(self, name: str) -> bool:
        try:
            self.analyte(name)
            return True
        except ConfigError:
            return False

    def output_analytes(self) -> list[str]:
        """Analytes that appear in the output, i.e. everything except the
        internal standard."""
        return [a.name for a in self.analytes if not a.is_internal_standard]

    def internal_standard_spec(self) -> AnalyteSpec:
        for a in self.analytes:
            if a.is_internal_standard:
                return a
        raise ConfigError("No analyte is marked as the internal standard")

    # -- (de)serialisation ---------------------------------------------------

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ratio_pairs"] = [list(pair) for pair in self.ratio_pairs]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Config":
        try:
            analytes = [AnalyteSpec(**a) for a in d["analytes"]]
            dilution = DilutionChain(**d["dilution"])
            cfg = Config(
                analytes=analytes,
                dilution=dilution,
                internal_standard=d.get("internal_standard", "DHBA"),
                std_step=d.get("std_step", "F"),
                round_decimals=d.get("round_decimals", 3),
                ratio_pairs=[tuple(p) for p in d.get("ratio_pairs", [])],
                output_order=list(d.get("output_order", [])),
                decimal_separator=d.get("decimal_separator", "."),
            )
        except (KeyError, TypeError) as exc:
            raise ConfigError(f"Malformed config: {exc}") from exc
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.analytes:
            raise ConfigError("Config has no analytes")
        names = [a.name for a in self.analytes]
        if len(set(normalize_analyte_name(n) for n in names)) != len(names):
            raise ConfigError("Duplicate analyte names in config")
        internal = [a for a in self.analytes if a.is_internal_standard]
        if len(internal) != 1:
            raise ConfigError(
                f"Exactly one analyte must be the internal standard, found {len(internal)}"
            )
        if self.std_step.upper() not in ("E", "F"):
            raise ConfigError("std_step must be 'E' or 'F'")
        if self.decimal_separator not in (".", ","):
            raise ConfigError("decimal_separator must be '.' or ','")
        for a in self.analytes:
            if not a.is_internal_standard and a.standard_weight_mg is None:
                raise ConfigError(f"{a.name}: standard_weight_mg is required")
            if a.apply_mw_correction and a.mw_ratio is None:
                raise ConfigError(f"{a.name}: MW correction enabled but no mw_ratio set")

    # -- persistence ---------------------------------------------------------

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @staticmethod
    def load(path: Path) -> "Config":
        data = json.loads(path.read_text(encoding="utf-8"))
        return Config.from_dict(data)


def normalize_analyte_name(name: str) -> str:
    """e.g. '5-HIAA' -> '5HIAA', '5-HT' -> '5HT'. Matches the R script's
    normalisation in mw_correct()."""
    return re.sub(r"[^A-Z0-9]", "", name.upper())


# ---------------------------------------------------------------------------
# Loading defaults / active config / presets
# ---------------------------------------------------------------------------

def load_defaults() -> Config:
    return Config.load(DEFAULTS_PATH)


def load_active_or_defaults() -> Config:
    """The config the app should start with: the last-saved active config if
    present and valid, otherwise the shipped defaults."""
    if ACTIVE_CONFIG_PATH.exists():
        try:
            return Config.load(ACTIVE_CONFIG_PATH)
        except (ConfigError, json.JSONDecodeError, OSError):
            pass
    return load_defaults()


def save_active(config: Config) -> None:
    config.validate()
    config.save(ACTIVE_CONFIG_PATH)


def reset_to_defaults() -> Config:
    cfg = load_defaults()
    save_active(cfg)
    return cfg


# -- presets ------------------------------------------------------------------

_PRESET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}$")


def _preset_path(name: str) -> Path:
    if not _PRESET_NAME_RE.match(name):
        raise ConfigError(
            "Preset name must be 1-80 characters, start with a letter/number, "
            "and contain only letters, numbers, spaces, '.', '_' or '-'."
        )
    return PRESETS_DIR / f"{name}.json"


def list_presets() -> list[str]:
    if not PRESETS_DIR.exists():
        return []
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


def save_preset(name: str, config: Config) -> Path:
    config.validate()
    path = _preset_path(name)
    config.save(path)
    return path


def load_preset(name: str) -> Config:
    return Config.load(_preset_path(name))


def delete_preset(name: str) -> None:
    path = _preset_path(name)
    if path.exists():
        path.unlink()


def export_preset(config: Config, dest: Path) -> None:
    """Write a preset to an arbitrary path (e.g. to share via email)."""
    config.validate()
    config.save(dest)


def import_preset(src: Path, name: str) -> Config:
    """Read a config from an arbitrary path and store it as a named preset."""
    cfg = Config.load(src)
    save_preset(name, cfg)
    return cfg
