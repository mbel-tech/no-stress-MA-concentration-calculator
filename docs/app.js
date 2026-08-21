"use strict";
/*
 * no-stress MA concentration calculator -- web version.
 *
 * A client-side-only port of monoamine_calc/engine.py, config.py and
 * parsing.py (the Python desktop app in this repo). No server, no build
 * step -- everything below runs in the browser once this page loads.
 *
 * Config JSON produced/consumed here uses the exact same schema as the
 * desktop app's config files, so a config downloaded from one can be
 * loaded into the other.
 */

const STORAGE_KEY = "no-stress-ma-web-config-v1";

const SAMPLE_COLUMNS = ["SAMPLE_ID", "MHPG", "NE", "DHBA", "DOPAC", "DA", "5-HIAA", "5-HT", "PROTEIN", "VOLUME"];
const STANDARD_COLUMNS = ["STD_ID", "MHPG", "NE", "DHBA", "DOPAC", "DA", "5-HIAA", "5-HT"];
const SAMPLE_NUMERIC_COLUMNS = SAMPLE_COLUMNS.filter((c) => c !== "SAMPLE_ID");
const STANDARD_NUMERIC_COLUMNS = STANDARD_COLUMNS.filter((c) => c !== "STD_ID");

const EXAMPLE_SAMPLES_TSV =
  "SAMPLE_ID\tMHPG\tNE\tDHBA\tDOPAC\tDA\t5-HIAA\t5-HT\tPROTEIN\tVOLUME\n" +
  "A1\t90\t210\t480\t310\t390\t240\t360\t1.5\t0.1\n" +
  "A2\t130\t170\t530\t270\t430\t280\t320\t2.0\t0.1";

const EXAMPLE_STANDARDS_TSV =
  "STD_ID\tMHPG\tNE\tDHBA\tDOPAC\tDA\t5-HIAA\t5-HT\n" +
  "S1\t100\t200\t500\t300\t400\t250\t350\n" +
  "S2\t120\t180\t520\t280\t420\t270\t330";

// Same values as monoamine_calc/defaults.json (and docs/defaults.json,
// which is kept for download/import compatibility with the desktop app).
const DEFAULTS = {
  analytes: [
    { name: "MHPG", standard_weight_mg: 9.78, mw_ratio: 0.810486104, apply_mw_correction: false, formula: "(C9H12O4)2 C4H10N2", is_internal_standard: false },
    { name: "NE", standard_weight_mg: 15.04, mw_ratio: 0.822694209, apply_mw_correction: true, formula: "C8H11NO3 HCL", is_internal_standard: false },
    { name: "DHBA", standard_weight_mg: null, mw_ratio: 0.632325536, apply_mw_correction: false, formula: "C7H9NO2 BrH", is_internal_standard: true },
    { name: "DOPAC", standard_weight_mg: 4.44, mw_ratio: null, apply_mw_correction: false, formula: null, is_internal_standard: false },
    { name: "DA", standard_weight_mg: 10.78, mw_ratio: 0.807735771, apply_mw_correction: true, formula: "C8H11NO2 HCl", is_internal_standard: false },
    { name: "5-HIAA", standard_weight_mg: 8.40, mw_ratio: null, apply_mw_correction: false, formula: null, is_internal_standard: false },
    { name: "5-HT", standard_weight_mg: 23.50, mw_ratio: 0.746839001, apply_mw_correction: true, formula: "C14H19N5O2 H2O4S", is_internal_standard: false },
  ],
  dilution: {
    step_a_divisor: 10.0,
    step_b_multiplier: 20000.0,
    step_c_multiplier: 0.02,
    step_d_divisor: 5.0,
    step_e_divisor: 6.0,
    step_f_divisor: 10.0,
  },
  internal_standard: "DHBA",
  std_step: "F",
  round_decimals: 3,
  ratio_pairs: [["MHPG", "NE"], ["DOPAC", "DA"], ["5-HIAA", "5-HT"]],
  output_order: ["SAMPLE_ID", "5-HT", "5-HIAA", "5-HIAA/5-HT", "DA", "DOPAC", "DOPAC/DA", "NE", "MHPG", "MHPG/NE"],
  decimal_separator: ".",
};

function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

// ---------------------------------------------------------------------------
// Config validation (mirrors Config.validate() in config.py)
// ---------------------------------------------------------------------------

function normalizeAnalyteName(name) {
  return String(name).toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function validateConfig(cfg) {
  if (!cfg.analytes || !cfg.analytes.length) throw new Error("Config has no analytes");
  const names = cfg.analytes.map((a) => a.name);
  const normSet = new Set(names.map(normalizeAnalyteName));
  if (normSet.size !== names.length) throw new Error("Duplicate analyte names in config");
  const internal = cfg.analytes.filter((a) => a.is_internal_standard);
  if (internal.length !== 1) {
    throw new Error(`Exactly one analyte must be the internal standard, found ${internal.length}`);
  }
  if (!["E", "F"].includes(String(cfg.std_step).toUpperCase())) {
    throw new Error("std_step must be 'E' or 'F'");
  }
  if (![".", ","].includes(cfg.decimal_separator)) {
    throw new Error("decimal_separator must be '.' or ','");
  }
  for (const a of cfg.analytes) {
    if (!a.is_internal_standard && (a.standard_weight_mg === null || a.standard_weight_mg === undefined || Number.isNaN(a.standard_weight_mg))) {
      throw new Error(`${a.name}: standard_weight_mg is required`);
    }
    if (a.apply_mw_correction && (a.mw_ratio === null || a.mw_ratio === undefined || Number.isNaN(a.mw_ratio))) {
      throw new Error(`${a.name}: MW correction enabled but no mw_ratio set`);
    }
  }
}

// ---------------------------------------------------------------------------
// Parsing (mirrors parsing.py)
// ---------------------------------------------------------------------------

function parseNumber(value, decimalSeparator) {
  if (value === null || value === undefined) return NaN;
  if (typeof value === "number") return value;
  let s = String(value).trim();
  if (s === "" || ["na", "nan", "n/a", "-"].includes(s.toLowerCase())) return NaN;
  if (decimalSeparator === ",") {
    s = s.split(".").join("").split(",").join(".");
  } else {
    s = s.split(",").join("");
  }
  const m = s.match(/[-+]?\d*\.?\d+/);
  if (!m) return NaN;
  const v = parseFloat(m[0]);
  return Number.isNaN(v) ? NaN : v;
}

function readDelimitedText(text) {
  const trimmed = text.replace(/^[\r\n]+|[\r\n]+$/g, "");
  if (!trimmed.trim()) throw new Error("No data provided.");
  const lines = trimmed.split(/\r\n|\r|\n/).filter((l) => l.trim() !== "");
  const sep = lines[0].includes("\t") ? "\t" : ",";
  const rows = lines.map((l) => l.split(sep));
  return { header: rows[0], body: rows.slice(1) };
}

function assignColumns(header, body, expected, label) {
  const notes = [];
  if (header.length !== expected.length) {
    throw new Error(`${label} must have ${expected.length} columns; found ${header.length} (${header.join(", ")}).`);
  }
  const expectedNorm = expected.map(normalizeAnalyteName);
  const actualNorm = header.map((h) => normalizeAnalyteName(String(h)));

  const sortedEq = (a, b) => {
    const sa = [...a].sort();
    const sb = [...b].sort();
    return sa.length === sb.length && sa.every((v, i) => v === sb[i]);
  };

  let colOrder;
  if (sortedEq(expectedNorm, actualNorm)) {
    colOrder = expectedNorm.map((e) => actualNorm.indexOf(e));
  } else {
    colOrder = expected.map((_, i) => i);
    notes.push(
      `${label}: column headers did not match the expected names by text, so columns were assigned by position: ` +
        `${expected.join(", ")}. Original headers were: ${header.join(", ")}.`
    );
  }

  const rows = body.map((r) => {
    const obj = {};
    expected.forEach((name, i) => {
      const raw = r[colOrder[i]];
      obj[name] = raw !== undefined ? raw.trim() : "";
    });
    return obj;
  });
  return { rows, notes };
}

function coerceNumericColumns(rows, columns, decimalSeparator) {
  return rows.map((r) => {
    const out = { ...r };
    columns.forEach((c) => {
      out[c] = parseNumber(r[c], decimalSeparator);
    });
    return out;
  });
}

function checkMissingIds(rows, idCol, label) {
  const missing = rows.some((r) => r[idCol] === undefined || String(r[idCol]).trim() === "");
  if (missing) throw new Error(`${label}: one or more rows are missing a ${idCol}.`);
}

function loadSamples(text, decimalSeparator) {
  const { header, body } = readDelimitedText(text);
  const { rows, notes } = assignColumns(header, body, SAMPLE_COLUMNS, "samples");
  const numeric = coerceNumericColumns(rows, SAMPLE_NUMERIC_COLUMNS, decimalSeparator);
  checkMissingIds(numeric, "SAMPLE_ID", "samples");
  return { rows: numeric, notes };
}

function loadStandards(text, decimalSeparator) {
  const { header, body } = readDelimitedText(text);
  const { rows, notes } = assignColumns(header, body, STANDARD_COLUMNS, "standards");
  const numeric = coerceNumericColumns(rows, STANDARD_NUMERIC_COLUMNS, decimalSeparator);
  checkMissingIds(numeric, "STD_ID", "standards");
  return { rows: numeric, notes };
}

// ---------------------------------------------------------------------------
// Engine (mirrors engine.py)
// ---------------------------------------------------------------------------

function buildStdChain(cfg) {
  const d = cfg.dilution;
  const rows = [];
  for (const a of cfg.analytes) {
    if (a.is_internal_standard) continue;
    if (a.standard_weight_mg === null || a.standard_weight_mg === undefined) {
      throw new Error(`${a.name}: no standard weight configured`);
    }
    const stepA = a.standard_weight_mg / d.step_a_divisor;
    const stepB = stepA * d.step_b_multiplier;
    const stepC = stepB * d.step_c_multiplier;
    const stepD = stepC / d.step_d_divisor;
    let correctedD;
    if (a.apply_mw_correction) {
      if (a.mw_ratio === null || a.mw_ratio === undefined) {
        throw new Error(`${a.name}: MW correction enabled but no ratio set`);
      }
      correctedD = stepD * a.mw_ratio;
    } else {
      correctedD = stepD;
    }
    const stepE = correctedD / d.step_e_divisor;
    const stepF = stepE / d.step_f_divisor;
    rows.push({
      Analyte: a.name,
      weight_mg: a.standard_weight_mg,
      step_a: stepA,
      step_b: stepB,
      step_c: stepC,
      step_d: stepD,
      corrected_d: correctedD,
      step_e: stepE,
      step_f: stepF,
    });
  }
  return rows;
}

function meanStandardAreas(standardRows, analyteCols) {
  const means = {};
  for (const col of analyteCols) {
    const vals = standardRows.map((r) => r[col]).filter((v) => !Number.isNaN(v));
    means[col] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : NaN;
  }
  return means;
}

function findColumnKey(keys, normalizedKey) {
  for (const k of keys) {
    if (normalizeAnalyteName(k) === normalizedKey) return k;
  }
  return null;
}

function computeK(sampleRows, meanAreas, cfg) {
  const internal = cfg.analytes.find((a) => a.is_internal_standard);
  if (!internal) throw new Error("No analyte is marked as the internal standard");
  const key = normalizeAnalyteName(internal.name);

  const meanKey = findColumnKey(Object.keys(meanAreas), key);
  if (meanKey === null) throw new Error(`Could not find internal standard '${internal.name}' in standards data`);
  const stdAvgInternal = meanAreas[meanKey];
  if (Number.isNaN(stdAvgInternal)) {
    throw new Error(`Could not obtain a single, non-NA standard average for ${internal.name}.`);
  }

  const sampleKeys = sampleRows.length ? Object.keys(sampleRows[0]) : SAMPLE_COLUMNS;
  const sampleInternalCol = findColumnKey(sampleKeys, key);
  if (sampleInternalCol === null) throw new Error(`Could not find internal standard '${internal.name}' in samples data`);

  const warnings = [];
  const k = {};
  for (const r of sampleRows) {
    const denom = r[sampleInternalCol] * r.PROTEIN;
    const isZero = denom === 0 || Number.isNaN(denom);
    if (isZero) {
      k[r.SAMPLE_ID] = NaN;
      warnings.push(
        `Sample ${r.SAMPLE_ID}: ${internal.name} area or PROTEIN is zero/missing -- K could not be computed (shown as blank, not Infinity).`
      );
    } else {
      k[r.SAMPLE_ID] = (stdAvgInternal * r.VOLUME) / denom;
    }
  }
  return { k, warnings };
}

function outputAnalytes(cfg) {
  return cfg.analytes.filter((a) => !a.is_internal_standard).map((a) => a.name);
}

function computeConcentrations(sampleRows, stdChain, meanAreas, cfg) {
  const { k, warnings: kWarnings } = computeK(sampleRows, meanAreas, cfg);
  const warnings = [...kWarnings];
  const stepCol = String(cfg.std_step).toUpperCase() === "E" ? "step_e" : "step_f";
  const outAnalytes = outputAnalytes(cfg);

  const wide = sampleRows.map((r) => ({ SAMPLE_ID: r.SAMPLE_ID }));

  for (const analyte of outAnalytes) {
    const key = normalizeAnalyteName(analyte);
    const chainRow = stdChain.find((row) => normalizeAnalyteName(row.Analyte) === key);
    if (!chainRow) throw new Error(`No standard dilution chain entry for analyte: ${analyte}`);
    const stdConc = chainRow[stepCol];

    const meanKey = findColumnKey(Object.keys(meanAreas), key);
    if (meanKey === null) throw new Error(`No standard peak-area data for analyte: ${analyte}`);
    const meanArea = meanAreas[meanKey];

    const sampleKeys = sampleRows.length ? Object.keys(sampleRows[0]) : SAMPLE_COLUMNS;
    const sampleCol = findColumnKey(sampleKeys, key);
    if (sampleCol === null) throw new Error(`No sample peak-area data for analyte: ${analyte}`);

    if (Number.isNaN(meanArea) || meanArea === 0) {
      warnings.push(`Analyte ${analyte}: mean standard area is zero/missing -- concentration could not be computed for any sample.`);
      sampleRows.forEach((r, i) => {
        wide[i][analyte] = NaN;
      });
    } else {
      const ratio = stdConc / meanArea;
      sampleRows.forEach((r, i) => {
        wide[i][analyte] = k[r.SAMPLE_ID] * r[sampleCol] * ratio;
      });
    }
  }
  return { wide, k, warnings };
}

function addRatios(wide, cfg) {
  return wide.map((row) => {
    const out = { ...row };
    for (const [num, den] of cfg.ratio_pairs) {
      if (!(num in row) || !(den in row)) continue;
      const n = row[num];
      const dd = row[den];
      out[`${num}/${den}`] = Number.isNaN(n) || Number.isNaN(dd) || dd === 0 ? NaN : n / dd;
    }
    return out;
  });
}

function roundAndOrder(wide, cfg) {
  const dec = cfg.round_decimals;
  const factor = Math.pow(10, dec);
  const rounded = wide.map((row) => {
    const out = {};
    for (const [key, val] of Object.entries(row)) {
      out[key] = key === "SAMPLE_ID" || Number.isNaN(val) ? val : Math.round(val * factor) / factor;
    }
    return out;
  });
  const allCols = rounded.length ? Object.keys(rounded[0]) : cfg.output_order;
  const ordered = cfg.output_order.filter((c) => allCols.includes(c));
  const remaining = allCols.filter((c) => !ordered.includes(c));
  return { columns: [...ordered, ...remaining], rows: rounded };
}

function runEngine(sampleRows, standardRows, cfg) {
  validateConfig(cfg);
  const stdChain = buildStdChain(cfg);
  const meanAreas = meanStandardAreas(standardRows, STANDARD_NUMERIC_COLUMNS);
  const { wide, k, warnings } = computeConcentrations(sampleRows, stdChain, meanAreas, cfg);
  const withRatios = addRatios(wide, cfg);
  const { columns, rows } = roundAndOrder(withRatios, cfg);
  return { columns, rows, stdChain, meanAreas, k, warnings };
}

// ---------------------------------------------------------------------------
// Config persistence (localStorage stands in for the desktop app's
// ~/.no-stress-ma/config.json "active config")
// ---------------------------------------------------------------------------

function loadActiveConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const cfg = JSON.parse(raw);
      validateConfig(cfg);
      return cfg;
    }
  } catch (e) {
    // fall through to defaults on any malformed/incompatible saved config
  }
  return deepClone(DEFAULTS);
}

function saveActiveConfig(cfg) {
  validateConfig(cfg);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg));
}

// ---------------------------------------------------------------------------
// UI state
// ---------------------------------------------------------------------------

let config = loadActiveConfig();
let samplesData = null; // { rows, notes }
let standardsData = null;
let lastResult = null;

const $ = (id) => document.getElementById(id);

function fmt(val, dec) {
  if (val === null || val === undefined || Number.isNaN(val)) return "";
  return Number(val).toFixed(dec);
}

// ---- tabs -------------------------------------------------------------

function initTabs() {
  document.querySelectorAll(".tab-button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-button").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(btn.dataset.tab).classList.add("active");
    });
  });
}

// ---- Data tab -----------------------------------------------------------

function initDataTab() {
  $("decimalSeparator").value = config.decimal_separator;
  $("decimalSeparator").addEventListener("change", (e) => {
    config.decimal_separator = e.target.value;
    saveActiveConfig(config);
  });

  $("loadExampleBtn").addEventListener("click", () => {
    $("samplesText").value = EXAMPLE_SAMPLES_TSV;
    $("standardsText").value = EXAMPLE_STANDARDS_TSV;
    parseDataPanel("samples");
    parseDataPanel("standards");
  });

  $("samplesText").addEventListener("input", () => parseDataPanel("samples"));
  $("standardsText").addEventListener("input", () => parseDataPanel("standards"));
  $("clearSamplesBtn").addEventListener("click", () => {
    $("samplesText").value = "";
    parseDataPanel("samples");
  });
  $("clearStandardsBtn").addEventListener("click", () => {
    $("standardsText").value = "";
    parseDataPanel("standards");
  });
}

function parseDataPanel(which) {
  const isSamples = which === "samples";
  const textEl = $(isSamples ? "samplesText" : "standardsText");
  const statusEl = $(isSamples ? "samplesStatus" : "standardsStatus");
  const text = textEl.value;

  if (!text.trim()) {
    if (isSamples) samplesData = null;
    else standardsData = null;
    statusEl.textContent = "";
    statusEl.className = "field-status";
    updateCalculateAvailability();
    return;
  }

  try {
    const result = isSamples ? loadSamples(text, config.decimal_separator) : loadStandards(text, config.decimal_separator);
    if (isSamples) samplesData = result;
    else standardsData = result;
    const label = isSamples ? "sample" : "standard";
    let msg = `Parsed ${result.rows.length} ${label} row${result.rows.length === 1 ? "" : "s"}.`;
    if (result.notes.length) msg += " " + result.notes.join(" ");
    statusEl.textContent = msg;
    statusEl.className = result.notes.length ? "field-status warn" : "field-status ok";
  } catch (err) {
    if (isSamples) samplesData = null;
    else standardsData = null;
    statusEl.textContent = err.message;
    statusEl.className = "field-status error";
  }
  updateCalculateAvailability();
}

function updateCalculateAvailability() {
  const btn = $("calculateBtn");
  const ready = !!(samplesData && samplesData.rows.length && standardsData && standardsData.rows.length);
  btn.disabled = !ready;
  $("calculateHint").textContent = ready ? "" : "Load samples and standards on the Data tab first.";
}

// ---- Constants tab --------------------------------------------------------

function initConstantsTab() {
  renderConstantsForm();

  $("applyConstantsBtn").addEventListener("click", () => {
    try {
      readConstantsForm();
      saveActiveConfig(config);
      setConstantsStatus("Saved.", false);
    } catch (err) {
      setConstantsStatus(err.message, true);
    }
  });

  $("resetConstantsBtn").addEventListener("click", () => {
    config = deepClone(DEFAULTS);
    saveActiveConfig(config);
    renderConstantsForm();
    setConstantsStatus("Reset to the original R script's values.", false);
  });

  $("downloadConfigBtn").addEventListener("click", () => {
    try {
      readConstantsForm();
      downloadJson(config, "no-stress-ma-config.json");
    } catch (err) {
      setConstantsStatus(err.message, true);
    }
  });

  $("loadConfigFile").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const loaded = JSON.parse(reader.result);
        validateConfig(loaded);
        config = loaded;
        saveActiveConfig(config);
        renderConstantsForm();
        setConstantsStatus(`Loaded config from ${file.name}.`, false);
      } catch (err) {
        setConstantsStatus(`Could not load ${file.name}: ${err.message}`, true);
      }
      e.target.value = "";
    };
    reader.readAsText(file);
  });
}

function setConstantsStatus(msg, isError) {
  const el = $("constantsStatus");
  el.textContent = msg;
  el.className = isError ? "field-status error" : "field-status ok";
}

function renderConstantsForm() {
  const tbody = $("analyteTableBody");
  tbody.innerHTML = "";
  config.analytes.forEach((a, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${a.name}</td>
      <td><input type="number" step="any" data-idx="${i}" data-field="standard_weight_mg"
            value="${a.standard_weight_mg === null || a.standard_weight_mg === undefined ? "" : a.standard_weight_mg}"
            ${a.is_internal_standard ? "disabled placeholder=\"n/a (internal std)\"" : ""}></td>
      <td><input type="number" step="any" data-idx="${i}" data-field="mw_ratio"
            value="${a.mw_ratio === null || a.mw_ratio === undefined ? "" : a.mw_ratio}"></td>
      <td class="center"><input type="checkbox" data-idx="${i}" data-field="apply_mw_correction" ${a.apply_mw_correction ? "checked" : ""}
            ${a.is_internal_standard ? "disabled" : ""}></td>
      <td class="formula">${a.formula || ""}</td>
      <td class="center"><input type="radio" name="internalStandard" data-idx="${i}" ${a.is_internal_standard ? "checked" : ""}></td>
    `;
    tbody.appendChild(tr);
  });

  const d = config.dilution;
  $("stepADivisor").value = d.step_a_divisor;
  $("stepBMultiplier").value = d.step_b_multiplier;
  $("stepCMultiplier").value = d.step_c_multiplier;
  $("stepDDivisor").value = d.step_d_divisor;
  $("stepEDivisor").value = d.step_e_divisor;
  $("stepFDivisor").value = d.step_f_divisor;
  $("stdStep").value = config.std_step;
  $("roundDecimals").value = config.round_decimals;
}

function readConstantsForm() {
  const next = deepClone(config);

  document.querySelectorAll("#analyteTableBody tr").forEach((tr, i) => {
    const weightInput = tr.querySelector('[data-field="standard_weight_mg"]');
    const ratioInput = tr.querySelector('[data-field="mw_ratio"]');
    const correctionInput = tr.querySelector('[data-field="apply_mw_correction"]');
    const internalRadio = tr.querySelector('[name="internalStandard"]');

    next.analytes[i].standard_weight_mg = weightInput.value === "" ? null : parseFloat(weightInput.value);
    next.analytes[i].mw_ratio = ratioInput.value === "" ? null : parseFloat(ratioInput.value);
    next.analytes[i].apply_mw_correction = correctionInput.checked;
    next.analytes[i].is_internal_standard = internalRadio.checked;
  });

  next.dilution.step_a_divisor = parseFloat($("stepADivisor").value);
  next.dilution.step_b_multiplier = parseFloat($("stepBMultiplier").value);
  next.dilution.step_c_multiplier = parseFloat($("stepCMultiplier").value);
  next.dilution.step_d_divisor = parseFloat($("stepDDivisor").value);
  next.dilution.step_e_divisor = parseFloat($("stepEDivisor").value);
  next.dilution.step_f_divisor = parseFloat($("stepFDivisor").value);
  next.std_step = $("stdStep").value;
  next.round_decimals = parseInt($("roundDecimals").value, 10);

  const internal = next.analytes.find((a) => a.is_internal_standard);
  if (internal) next.internal_standard = internal.name;

  validateConfig(next);
  config = next;
}

function downloadJson(obj, filename) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---- Results tab --------------------------------------------------------

function initResultsTab() {
  $("calculateBtn").addEventListener("click", runCalculation);
  $("toggleChainBtn").addEventListener("click", () => {
    const el = $("chainSection");
    const visible = el.classList.toggle("visible");
    $("toggleChainBtn").textContent = visible ? "Hide standard dilution chain" : "Show standard dilution chain";
  });
  $("downloadCsvBtn").addEventListener("click", downloadResultsCsv);
  updateCalculateAvailability();
}

function runCalculation() {
  const statusEl = $("resultsStatus");
  try {
    readConstantsForm();
    saveActiveConfig(config);
    lastResult = runEngine(samplesData.rows, standardsData.rows, config);
    renderResults(lastResult);
    statusEl.textContent = "";
    statusEl.className = "field-status";
  } catch (err) {
    lastResult = null;
    statusEl.textContent = err.message;
    statusEl.className = "field-status error";
    $("resultsTableWrap").innerHTML = "";
    $("warningsBox").innerHTML = "";
    $("downloadCsvBtn").disabled = true;
  }
}

function renderResults(result) {
  const dec = config.round_decimals;

  // Warnings
  const warnBox = $("warningsBox");
  warnBox.innerHTML = "";
  if (result.warnings.length) {
    const title = document.createElement("div");
    title.className = "warnings-title";
    title.textContent = `${result.warnings.length} warning${result.warnings.length === 1 ? "" : "s"}:`;
    warnBox.appendChild(title);
    const ul = document.createElement("ul");
    result.warnings.forEach((w) => {
      const li = document.createElement("li");
      li.textContent = w;
      ul.appendChild(li);
    });
    warnBox.appendChild(ul);
    warnBox.className = "warnings-box visible";
  } else {
    warnBox.className = "warnings-box";
  }

  // Results table
  const wrap = $("resultsTableWrap");
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  thead.innerHTML = `<tr>${result.columns.map((c) => `<th>${c}</th>`).join("")}</tr>`;
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  result.rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = result.columns
      .map((c) => (c === "SAMPLE_ID" ? `<td>${row[c]}</td>` : `<td class="num">${fmt(row[c], dec)}</td>`))
      .join("");
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.innerHTML = "";
  wrap.appendChild(table);

  // Standard dilution chain preview
  const chainWrap = $("chainTableWrap");
  const chainTable = document.createElement("table");
  chainTable.innerHTML = `<thead><tr>
      <th>Analyte</th><th>Weight mg</th><th>Step A</th><th>Step B</th><th>Step C</th>
      <th>Step D</th><th>Corrected D</th><th>Step E</th><th>Step F</th>
    </tr></thead>`;
  const chainBody = document.createElement("tbody");
  result.stdChain.forEach((r) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.Analyte}</td><td class="num">${fmt(r.weight_mg, 4)}</td>
      <td class="num">${fmt(r.step_a, 4)}</td><td class="num">${fmt(r.step_b, 4)}</td>
      <td class="num">${fmt(r.step_c, 4)}</td><td class="num">${fmt(r.step_d, 4)}</td>
      <td class="num">${fmt(r.corrected_d, 6)}</td><td class="num">${fmt(r.step_e, 6)}</td>
      <td class="num">${fmt(r.step_f, 6)}</td>`;
    chainBody.appendChild(tr);
  });
  chainTable.appendChild(chainBody);
  chainWrap.innerHTML = "";
  chainWrap.appendChild(chainTable);

  $("downloadCsvBtn").disabled = false;
}

function downloadResultsCsv() {
  if (!lastResult) return;
  const dec = config.round_decimals;
  const lines = [lastResult.columns.join(",")];
  lastResult.rows.forEach((row) => {
    lines.push(
      lastResult.columns
        .map((c) => (c === "SAMPLE_ID" ? row[c] : fmt(row[c], dec)))
        .join(",")
    );
  });
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const today = new Date();
  const dd = String(today.getDate()).padStart(2, "0");
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const yy = String(today.getFullYear()).slice(-2);
  a.href = url;
  a.download = `monoamine concentration ${dd}.${mm}.${yy}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initDataTab();
    initConstantsTab();
    initResultsTab();
  });
}

// Node-only export for the automated numeric test suite (tests/web/*.test.js);
// a plain <script> load in the browser leaves `module` undefined, so this is a no-op there.
if (typeof module !== "undefined" && module.exports) {
  module.exports = { runEngine, loadSamples, loadStandards, validateConfig, deepClone, DEFAULTS, parseNumber, normalizeAnalyteName };
}
