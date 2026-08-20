"""Turn pasted/clipboard/file input into validated DataFrames.

Ported from the R script's:

    samples <- read.delim("clipboard", header = TRUE, sep = "\\t", ...)
    standards <- read.delim("clipboard", header = TRUE, sep = "\\t", ...)
    colnames(samples) <- expected_samples_cols     # blind positional overwrite
    ... readr::parse_number(as.character(.x)) ...

Two deliberate improvements over the R script:

1. Column matching prefers matching by *name* (case/punctuation-insensitive)
   over the R script's blind positional overwrite; positional fallback is
   still used, but the caller is told which one happened.
2. `parse_number` treats a configurable decimal separator, since a value
   like "1,5" means 1.5 on an Italian locale but 1500 (with a thousands
   separator) if parsed the R/US way.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import normalize_analyte_name

SAMPLE_COLUMNS = ["SAMPLE_ID", "MHPG", "NE", "DHBA", "DOPAC", "DA", "5-HIAA", "5-HT", "PROTEIN", "VOLUME"]
STANDARD_COLUMNS = ["STD_ID", "MHPG", "NE", "DHBA", "DOPAC", "DA", "5-HIAA", "5-HT"]

SAMPLE_NUMERIC_COLUMNS = [c for c in SAMPLE_COLUMNS if c != "SAMPLE_ID"]
STANDARD_NUMERIC_COLUMNS = [c for c in STANDARD_COLUMNS if c != "STD_ID"]


class ParsingError(ValueError):
    """Raised for structurally invalid input (mirrors the R script's stop())."""


@dataclass
class ParseResult:
    df: pd.DataFrame
    used_name_matching: bool
    notes: list[str]


# ---------------------------------------------------------------------------
# Reading raw tabular text (paste box / clipboard / file) into a DataFrame
# ---------------------------------------------------------------------------

def read_delimited_text(text: str) -> pd.DataFrame:
    """Read tab- or comma-separated pasted text with a header row."""
    text = text.strip("\n\r")
    if not text.strip():
        raise ParsingError("No data provided.")
    first_line = text.splitlines()[0]
    sep = "\t" if "\t" in first_line else ","
    try:
        df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, header=0, engine="python")
    except Exception as exc:  # pragma: no cover - defensive
        raise ParsingError(f"Could not parse pasted data: {exc}") from exc
    df = df.dropna(how="all")
    return df


def read_file(path: Path) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str, header=0)
    elif suffix in (".tsv",):
        df = pd.read_csv(path, sep="\t", dtype=str, header=0, engine="python")
    elif suffix in (".csv",):
        df = pd.read_csv(path, dtype=str, header=0, engine="python", sep=None)
    else:
        raise ParsingError(f"Unsupported file type: {suffix}")
    df = df.dropna(how="all")
    return df


# ---------------------------------------------------------------------------
# Column validation + assignment
# ---------------------------------------------------------------------------

def assign_columns(df: pd.DataFrame, expected: list[str], label: str) -> ParseResult:
    """Validate column count, then assign `expected` names -- preferring a
    name-based match (case/punctuation-insensitive) over the R script's
    blind positional overwrite. Falls back to positional with a note."""
    notes: list[str] = []
    if df.shape[1] != len(expected):
        raise ParsingError(
            f"{label} must have {len(expected)} columns; found {df.shape[1]} "
            f"({', '.join(str(c) for c in df.columns)})."
        )

    expected_norm = [normalize_analyte_name(c) for c in expected]
    actual_norm = [normalize_analyte_name(str(c)) for c in df.columns]

    if sorted(expected_norm) == sorted(actual_norm):
        # Reorder columns to match `expected` by name rather than assuming
        # the pasted order already matches.
        order = [actual_norm.index(e) for e in expected_norm]
        df = df.iloc[:, order]
        df.columns = expected
        return ParseResult(df=df, used_name_matching=True, notes=notes)

    # Positional fallback -- same behaviour as the R script, but flagged.
    notes.append(
        f"{label}: column headers did not match the expected names by text, "
        f"so columns were assigned by position: {', '.join(expected)}. "
        f"Original headers were: {', '.join(str(c) for c in df.columns)}."
    )
    df = df.copy()
    df.columns = expected
    return ParseResult(df=df, used_name_matching=False, notes=notes)


# ---------------------------------------------------------------------------
# Numeric coercion (readr::parse_number equivalent)
# ---------------------------------------------------------------------------

_NUMBER_RE_DOT = re.compile(r"[-+]?\d[\d,]*\.?\d*|\.\d+")
_NUMBER_RE_COMMA = re.compile(r"[-+]?\d[\d.]*,?\d*|,\d+")


def parse_number(value, decimal_separator: str = ".") -> float:
    """Extract the first number from a string, mirroring readr::parse_number:
    strips currency symbols, units, thousands separators, and other
    non-numeric characters.

    decimal_separator="." (default, matches the R script): "," is treated as
    a thousands separator and stripped, e.g. "1,234" -> 1234, "1,5" -> 15.
    decimal_separator=",": "." is treated as a thousands separator instead,
    e.g. "1.234" -> 1234, "1,5" -> 1.5.
    """
    if value is None:
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s == "" or s.lower() in ("na", "nan", "n/a", "-"):
        return float("nan")

    if decimal_separator == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")

    match = re.search(r"[-+]?\d*\.?\d+", s)
    if match is None:
        return float("nan")
    try:
        return float(match.group())
    except ValueError:
        return float("nan")


def coerce_numeric_columns(df: pd.DataFrame, columns: list[str], decimal_separator: str = ".") -> pd.DataFrame:
    df = df.copy()
    for col in columns:
        df[col] = df[col].apply(lambda v: parse_number(v, decimal_separator))
    return df


# ---------------------------------------------------------------------------
# High-level entry points
# ---------------------------------------------------------------------------

def load_samples(df: pd.DataFrame, decimal_separator: str = ".") -> ParseResult:
    result = assign_columns(df, SAMPLE_COLUMNS, "samples")
    result.df = coerce_numeric_columns(result.df, SAMPLE_NUMERIC_COLUMNS, decimal_separator)
    _check_missing_ids(result.df, "SAMPLE_ID", "samples")
    return result


def load_standards(df: pd.DataFrame, decimal_separator: str = ".") -> ParseResult:
    result = assign_columns(df, STANDARD_COLUMNS, "standards")
    result.df = coerce_numeric_columns(result.df, STANDARD_NUMERIC_COLUMNS, decimal_separator)
    _check_missing_ids(result.df, "STD_ID", "standards")
    return result


def _check_missing_ids(df: pd.DataFrame, id_col: str, label: str) -> None:
    if df[id_col].isna().any() or (df[id_col].astype(str).str.strip() == "").any():
        raise ParsingError(f"{label}: one or more rows are missing a {id_col}.")
