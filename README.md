# no-stress-MA-concentration-calculator

A plug-and-play desktop app that computes tissue monoamine concentrations
from HPLC peak areas, using a DHBA internal standard and an external
standard dilution series. It is a Python/tkinter port of
[`monoamine calculation program.R`](reference/monoamine%20calculation%20program.R),
with every fixed calibration number made editable and saveable.

No RStudio, no clipboard-juggling between two `read.delim("clipboard")`
calls, no hunting through R source to update a standard weight before a new
run.

## What it computes

For each sample, per analyte (MHPG, NE, DOPAC, DA, 5-HIAA, 5-HT):

1. **Standard dilution chain (A → F).** Each analyte's standard weight (mg)
   is walked through six fixed steps to a working concentration; DA, 5-HT
   and NE additionally get a molecular-weight correction (their standard
   salt's MW ratio) by default — see [Deviations](#deliberate-deviations-from-the-r-script).
2. **Mean standard peak area**, per analyte, across all standard rows.
3. **Per-sample multiplier K** = `(mean standard DHBA area × sample VOLUME) / (sample DHBA area × sample PROTEIN)`.
4. **Concentration** = `K × sample peak area × (standard concentration ÷ mean standard area)`.
5. **Ratios**: MHPG/NE, DOPAC/DA, 5-HIAA/5-HT.
6. Rounded to 3 decimals and exported as a styled `.xlsx`.

## Input format

Two datasets, exactly as the R script expected — tab-separated with a
header row, either pasted, read from the clipboard, or loaded from a
`.tsv`/`.csv`/`.xlsx` file:

**Samples** — `SAMPLE_ID, MHPG, NE, DHBA, DOPAC, DA, 5-HIAA, 5-HT, PROTEIN, VOLUME`
(PROTEIN in mg from a Bradford assay; VOLUME in mL — 0.1 mL is standard,
higher for a re-run).

**Standards** — `STD_ID, MHPG, NE, DHBA, DOPAC, DA, 5-HIAA, 5-HT`.

If the pasted/loaded headers match these names (ignoring case and
punctuation), columns are matched by name. Otherwise the app falls back to
assigning them by position — same as the R script — and tells you so.

Two small example files are included: [`examples/example_samples.tsv`](examples/example_samples.tsv)
and [`examples/example_standards.tsv`](examples/example_standards.tsv).

## Running it

All dependencies (`pandas`, `openpyxl`) plus `tkinter` ship with a normal
Python install, so on most machines nothing extra needs installing.

**Windows, easiest:** double-click [`Run Calculator.bat`](Run%20Calculator.bat).
It checks for Python, installs `pandas`/`openpyxl` on first run if missing,
and launches the app.

**From a terminal (any OS with Python 3.10+):**

```bash
pip install -r requirements.txt
python -m monoamine_calc
```

### Using the app

1. **Data tab** — load Samples and Standards (paste, read clipboard, or
   load a file). Set the decimal separator if your data uses commas.
2. **Constants tab** — review/edit standard weights, MW ratios, correction
   toggles, the six dilution-chain numbers, rounding, and which analyte is
   the internal standard. Save your edits as a named preset to reuse for a
   new standard batch, export it to share with a colleague, or reset to the
   original R script's values at any time.
3. Click **Calculate**. The **Results tab** shows the concentration table,
   any warnings, and an optional preview of the computed A→F standard
   chain. **Export to Excel** saves a `monoamine concentration DD.MM.YY.xlsx`
   file with the results plus two extra sheets (`std_chain`,
   `constants_used`) documenting exactly what produced them.

### Building a standalone .exe (optional)

For a colleague without Python installed:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "no-stress-MA-calculator" -m monoamine_calc
```

The `.exe` will be under `dist/`.

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

The test suite includes an end-to-end golden fixture with values
hand-derived from the R script's formulas, so a change that alters the
math will fail loudly.

## Deliberate deviations from the R script

Each of these is a fix, not a change to the maths itself:

- **Division-by-zero guard.** If a sample's DHBA area or PROTEIN is 0, the
  R script silently writes `Inf` to Excel. This app produces a blank
  (`NaN`) cell and lists the affected sample in a warnings panel.
- **Dead code dropped.** The R script computed a row-ordering variable
  twice (the first result was immediately overwritten and never used).
  Harmless, but not reproduced here — output values are unaffected, as row
  order was cosmetic.
- **Load-order bug fixed.** The R script used `dplyr`/`tidyr` functions
  before `library(dplyr)` was called, so it only worked if those packages
  happened to already be loaded in the R session.
- **A missing/duplicate DHBA standard average is still a hard stop** — shown
  as a dialog instead of a console error.

## Project layout

```
monoamine_calc/
├── defaults.json      # every constant from the R script, as editable data
├── config.py           # Config dataclasses, presets, load/save/reset
├── parsing.py           # clipboard/file -> validated DataFrame
├── engine.py             # the pure calculation, no I/O or GUI
├── excel_out.py           # styled .xlsx writer
└── gui/                    # tkinter front-end (Data / Constants / Results tabs)
tests/                        # pytest suite, incl. the golden-value fixture
examples/                      # sample input files
reference/                      # the original R script, kept for provenance
```

`engine.py` has no GUI or file-I/O imports — it is reusable directly from a
script or notebook if you'd rather not use the GUI.

## License

[MIT](LICENSE)
