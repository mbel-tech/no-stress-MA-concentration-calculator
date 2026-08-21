"use strict";
/*
 * Numeric parity test for docs/app.js against the same golden fixture used
 * by tests/test_engine.py -- values hand-derived from the R script's
 * formulas. Run with: node tests/web/engine.test.js
 */
const assert = require("assert");
const path = require("path");

const {
  runEngine,
  loadSamples,
  loadStandards,
  validateConfig,
  deepClone,
  DEFAULTS,
  parseNumber,
  normalizeAnalyteName,
} = require(path.join(__dirname, "..", "..", "docs", "app.js"));

function approxEqual(actual, expected, tolerance, msg) {
  assert.ok(
    Math.abs(actual - expected) < tolerance,
    `${msg}: expected ${expected}, got ${actual} (tolerance ${tolerance})`
  );
}

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok - ${name}`);
}

console.log("engine.test.js");

test("config validates and matches the shipped defaults.json shape", () => {
  const cfg = deepClone(DEFAULTS);
  validateConfig(cfg); // should not throw
  assert.strictEqual(cfg.analytes.length, 7);
  assert.strictEqual(cfg.analytes.filter((a) => a.is_internal_standard).length, 1);
});

test("standard dilution chain matches R-derived golden values to 9dp", () => {
  const cfg = deepClone(DEFAULTS);
  const samplesTsv =
    "SAMPLE_ID\tMHPG\tNE\tDHBA\tDOPAC\tDA\t5-HIAA\t5-HT\tPROTEIN\tVOLUME\nA1\t90\t210\t480\t310\t390\t240\t360\t1.5\t0.1";
  const standardsTsv = "STD_ID\tMHPG\tNE\tDHBA\tDOPAC\tDA\t5-HIAA\t5-HT\nS1\t100\t200\t500\t300\t400\t250\t350";
  const { rows: samples } = loadSamples(samplesTsv, ".");
  const { rows: standards } = loadStandards(standardsTsv, ".");
  const result = runEngine(samples, standards, cfg);

  const expected = {
    DOPAC: { step_d: 35.52, corrected_d: 35.52, step_e: 5.92, step_f: 0.592 },
    DA: { step_d: 86.24, corrected_d: 69.659132891, step_e: 11.609855482, step_f: 1.160985548 },
    "5-HIAA": { step_d: 67.2, corrected_d: 67.2, step_e: 11.2, step_f: 1.12 },
    "5-HT": { step_d: 188.0, corrected_d: 140.405732188, step_e: 23.400955365, step_f: 2.340095536 },
    NE: { step_d: 120.32, corrected_d: 98.986567227, step_e: 16.497761204, step_f: 1.64977612 },
    MHPG: { step_d: 78.24, corrected_d: 78.24, step_e: 13.04, step_f: 1.304 },
  };

  for (const [analyte, exp] of Object.entries(expected)) {
    const row = result.stdChain.find((r) => r.Analyte === analyte);
    assert.ok(row, `missing chain row for ${analyte}`);
    approxEqual(row.step_d, exp.step_d, 1e-6, `${analyte} step_d`);
    approxEqual(row.corrected_d, exp.corrected_d, 1e-6, `${analyte} corrected_d`);
    approxEqual(row.step_e, exp.step_e, 1e-6, `${analyte} step_e`);
    approxEqual(row.step_f, exp.step_f, 1e-6, `${analyte} step_f`);
  }
});

test("end-to-end golden fixture matches the Python/pytest expected output exactly", () => {
  const cfg = deepClone(DEFAULTS);
  const samplesTsv =
    "SAMPLE_ID\tMHPG\tNE\tDHBA\tDOPAC\tDA\t5-HIAA\t5-HT\tPROTEIN\tVOLUME\n" +
    "A1\t90\t210\t480\t310\t390\t240\t360\t1.5\t0.1\n" +
    "A2\t130\t170\t530\t270\t430\t280\t320\t2.0\t0.1";
  const standardsTsv =
    "STD_ID\tMHPG\tNE\tDHBA\tDOPAC\tDA\t5-HIAA\t5-HT\n" +
    "S1\t100\t200\t500\t300\t400\t250\t350\n" +
    "S2\t120\t180\t520\t280\t420\t270\t330";

  const { rows: samples } = loadSamples(samplesTsv, ".");
  const { rows: standards } = loadStandards(standardsTsv, ".");
  const result = runEngine(samples, standards, cfg);

  assert.strictEqual(result.warnings.length, 0, `expected no warnings, got: ${JSON.stringify(result.warnings)}`);

  approxEqual(result.k["A1"], 0.070833333, 1e-9, "K[A1]");
  approxEqual(result.k["A2"], 0.048113208, 1e-9, "K[A2]");

  const expectedRows = {
    A1: { "5-HT": 0.176, "5-HIAA": 0.073, "5-HIAA/5-HT": 0.417, DA: 0.078, DOPAC: 0.045, "DOPAC/DA": 0.573, NE: 0.129, MHPG: 0.076, "MHPG/NE": 0.585 },
    A2: { "5-HT": 0.106, "5-HIAA": 0.058, "5-HIAA/5-HT": 0.548, DA: 0.059, DOPAC: 0.027, "DOPAC/DA": 0.453, NE: 0.071, MHPG: 0.074, "MHPG/NE": 1.044 },
  };

  assert.deepStrictEqual(
    result.columns,
    ["SAMPLE_ID", "5-HT", "5-HIAA", "5-HIAA/5-HT", "DA", "DOPAC", "DOPAC/DA", "NE", "MHPG", "MHPG/NE"],
    "column order"
  );

  for (const row of result.rows) {
    const exp = expectedRows[row.SAMPLE_ID];
    assert.ok(exp, `unexpected sample id ${row.SAMPLE_ID}`);
    for (const [col, val] of Object.entries(exp)) {
      assert.strictEqual(row[col], val, `${row.SAMPLE_ID}.${col}: expected ${val}, got ${row[col]}`);
    }
  }
});

test("MHPG MW-correction toggle scales output by exactly the MW ratio", () => {
  const cfgOff = deepClone(DEFAULTS);
  const cfgOn = deepClone(DEFAULTS);
  cfgOn.analytes.find((a) => a.name === "MHPG").apply_mw_correction = true;
  cfgOff.round_decimals = 9;
  cfgOn.round_decimals = 9;

  const samplesTsv =
    "SAMPLE_ID\tMHPG\tNE\tDHBA\tDOPAC\tDA\t5-HIAA\t5-HT\tPROTEIN\tVOLUME\nA1\t90\t210\t480\t310\t390\t240\t360\t1.5\t0.1";
  const standardsTsv =
    "STD_ID\tMHPG\tNE\tDHBA\tDOPAC\tDA\t5-HIAA\t5-HT\nS1\t100\t200\t500\t300\t400\t250\t350\nS2\t120\t180\t520\t280\t420\t270\t330";
  const { rows: samples } = loadSamples(samplesTsv, ".");
  const { rows: standards } = loadStandards(standardsTsv, ".");

  const off = runEngine(deepClone(samples), deepClone(standards), cfgOff);
  const on = runEngine(deepClone(samples), deepClone(standards), cfgOn);

  const mwRatio = DEFAULTS.analytes.find((a) => a.name === "MHPG").mw_ratio;
  const mhpgOff = off.rows[0].MHPG;
  const mhpgOn = on.rows[0].MHPG;
  approxEqual(mhpgOn / mhpgOff, mwRatio, 1e-6, "MHPG on/off ratio should equal the MW ratio");

  // every other analyte must be untouched
  for (const col of ["5-HT", "5-HIAA", "DA", "DOPAC", "NE"]) {
    assert.strictEqual(off.rows[0][col], on.rows[0][col], `${col} should be unaffected by the MHPG toggle`);
  }
});

test("zero PROTEIN produces NaN (blank) K and a warning, not Infinity", () => {
  const cfg = deepClone(DEFAULTS);
  const samplesTsv =
    "SAMPLE_ID\tMHPG\tNE\tDHBA\tDOPAC\tDA\t5-HIAA\t5-HT\tPROTEIN\tVOLUME\nA1\t90\t210\t480\t310\t390\t240\t360\t0\t0.1";
  const standardsTsv =
    "STD_ID\tMHPG\tNE\tDHBA\tDOPAC\tDA\t5-HIAA\t5-HT\nS1\t100\t200\t500\t300\t400\t250\t350\nS2\t120\t180\t520\t280\t420\t270\t330";
  const { rows: samples } = loadSamples(samplesTsv, ".");
  const { rows: standards } = loadStandards(standardsTsv, ".");
  const result = runEngine(samples, standards, cfg);

  assert.ok(Number.isNaN(result.k["A1"]), "K should be NaN, not Infinity");
  assert.ok(result.warnings.some((w) => w.includes("A1")), "expected a warning mentioning sample A1");
  assert.ok(Number.isNaN(result.rows[0]["5-HT"]), "downstream concentration should also be NaN");
});

test("parseNumber matches readr::parse_number semantics under both decimal separators", () => {
  approxEqual(parseNumber("1,234", "."), 1234, 1e-9, '"1,234" with dot separator');
  approxEqual(parseNumber("1,5", "."), 15, 1e-9, '"1,5" with dot separator (comma = thousands sep)');
  approxEqual(parseNumber("1,5", ","), 1.5, 1e-9, '"1,5" with comma separator');
  approxEqual(parseNumber("1.234", ","), 1234, 1e-9, '"1.234" with comma separator (dot = thousands sep)');
  approxEqual(parseNumber("12 ng", "."), 12, 1e-9, '"12 ng" strips unit');
  assert.ok(Number.isNaN(parseNumber("", ".")), "empty string -> NaN");
  assert.ok(Number.isNaN(parseNumber("NA", ".")), '"NA" -> NaN');
});

test("normalizeAnalyteName ignores case and punctuation, matching the R script's mw_correct()", () => {
  assert.strictEqual(normalizeAnalyteName("5-HT"), "5HT");
  assert.strictEqual(normalizeAnalyteName("5HT"), "5HT");
  assert.strictEqual(normalizeAnalyteName("5-HIAA"), "5HIAA");
});

test("positional column fallback triggers with a note when headers don't match by name", () => {
  const samplesTsv = "ID\tA\tB\tC\tD\tE\tF\tG\tH\tI\nA1\t90\t210\t480\t310\t390\t240\t360\t1.5\t0.1";
  const { rows, notes } = loadSamples(samplesTsv, ".");
  assert.strictEqual(notes.length, 1, "expected one fallback note");
  assert.strictEqual(rows[0].SAMPLE_ID, "A1");
  assert.strictEqual(rows[0].MHPG, 90);
});

console.log(`\n${passed} passed`);
