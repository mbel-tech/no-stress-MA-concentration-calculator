"""Tests for clipboard/file -> DataFrame parsing: number coercion and
column-name vs positional matching."""
import math

import pandas as pd
import pytest

from monoamine_calc.parsing import (
    ParsingError,
    SAMPLE_COLUMNS,
    STANDARD_COLUMNS,
    assign_columns,
    load_samples,
    load_standards,
    parse_number,
    read_delimited_text,
)


# ---------------------------------------------------------------------------
# parse_number (readr::parse_number equivalent)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("123", 123.0),
    ("123.45", 123.45),
    ("12 ng", 12.0),
    ("$45.6", 45.6),
    ("", None),   # NaN
    ("NA", None),  # NaN
    ("-5.5", -5.5),
])
def test_parse_number_dot_separator(raw, expected):
    result = parse_number(raw, ".")
    if expected is None:
        assert math.isnan(result)
    else:
        assert result == pytest.approx(expected)


def test_parse_number_dot_separator_treats_comma_as_thousands():
    assert parse_number("1,234", ".") == pytest.approx(1234.0)
    assert parse_number("1,5", ".") == pytest.approx(15.0)


def test_parse_number_comma_separator_treats_dot_as_thousands():
    assert parse_number("1.234", ",") == pytest.approx(1234.0)
    assert parse_number("1,5", ",") == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Reading pasted text
# ---------------------------------------------------------------------------

def test_read_delimited_text_detects_tab_separator():
    text = "A\tB\tC\n1\t2\t3\n"
    df = read_delimited_text(text)
    assert list(df.columns) == ["A", "B", "C"]
    assert df.iloc[0].tolist() == ["1", "2", "3"]


def test_read_delimited_text_rejects_empty_input():
    with pytest.raises(ParsingError):
        read_delimited_text("   \n  ")


# ---------------------------------------------------------------------------
# Column assignment: name match vs positional fallback
# ---------------------------------------------------------------------------

def test_assign_columns_matches_by_name_and_reorders():
    # headers present but in a different order, different case/punctuation
    df = pd.DataFrame(
        [["1", "480", "90"]],
        columns=["sample_id", "dhba", "MHPG"],
    )
    result = assign_columns(df, ["SAMPLE_ID", "MHPG", "DHBA"], "test")
    assert result.used_name_matching is True
    assert result.notes == []
    assert result.df.columns.tolist() == ["SAMPLE_ID", "MHPG", "DHBA"]
    assert result.df.iloc[0]["MHPG"] == "90"
    assert result.df.iloc[0]["DHBA"] == "480"


def test_assign_columns_falls_back_to_positional_with_note():
    df = pd.DataFrame([["1", "480"]], columns=["x", "y"])
    result = assign_columns(df, ["SAMPLE_ID", "DHBA"], "test")
    assert result.used_name_matching is False
    assert len(result.notes) == 1
    assert "position" in result.notes[0]
    assert result.df.columns.tolist() == ["SAMPLE_ID", "DHBA"]


def test_assign_columns_rejects_wrong_column_count():
    df = pd.DataFrame([["1", "2"]], columns=["a", "b"])
    with pytest.raises(ParsingError):
        assign_columns(df, ["SAMPLE_ID", "MHPG", "DHBA"], "test")


# ---------------------------------------------------------------------------
# load_samples / load_standards end-to-end
# ---------------------------------------------------------------------------

def test_load_samples_coerces_numeric_columns():
    df = pd.DataFrame(
        [["A1", "90", "210", "480", "310", "390", "240", "360", "1.5", "0.1"]],
        columns=SAMPLE_COLUMNS,
    )
    result = load_samples(df, ".")
    assert result.df["PROTEIN"][0] == pytest.approx(1.5)
    assert result.df["DHBA"][0] == pytest.approx(480.0)
    assert result.df["SAMPLE_ID"][0] == "A1"


def test_load_standards_coerces_numeric_columns():
    df = pd.DataFrame(
        [["S1", "100", "200", "500", "300", "400", "250", "350"]],
        columns=STANDARD_COLUMNS,
    )
    result = load_standards(df, ".")
    assert result.df["DHBA"][0] == pytest.approx(500.0)


def test_load_samples_rejects_missing_sample_id():
    df = pd.DataFrame(
        [["", "90", "210", "480", "310", "390", "240", "360", "1.5", "0.1"]],
        columns=SAMPLE_COLUMNS,
    )
    with pytest.raises(ParsingError):
        load_samples(df, ".")
