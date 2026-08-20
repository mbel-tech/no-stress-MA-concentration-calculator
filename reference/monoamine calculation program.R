



###GUIDELINES FOR "SAMPLES" DATASET :
# COLUMN ORDER MUST BE:
# SAMPLE_ID - MHPG - NE	- DHBA -	DOPAC -	DA -	5-HIAA -	5-HT - PROTEIN - VOLUME
## PROTEIN (MG) --> PROTEIN RECOVERY FROM BRADFORD ASSAY
## VOLUME (ML) --> VOLUME OF BUFFER USED : STANDARD IS 0.1 ML, BUT HIGHER IF IT IS A RE-RUN

samples <- read.delim("clipboard", header = TRUE, sep = "\t", stringsAsFactors = FALSE)

###GUIDELINES FOR "STANDARD" DATASET :
# COLUMN ORDER MUST BE:
# STD_ID - MHPG - NE	- DHBA -	DOPAC -	DA -	5-HIAA -	5-HT

standards <- read.delim("clipboard", header = TRUE, sep = "\t", stringsAsFactors = FALSE)

# ---- IMPORTANT: INSERT HERE THE STD DILUITION USED (CAN BE E or F ) ----

std_step_used <- "F"  # allowed: "E","e","F","f"

# Coerce/validate to either "E" or "F"
std_step_used <- toupper(trimws(std_step_used))
if (!std_step_used %in% c("E", "F")) stop("std_step_used must be one of: E/e or F/f")


### Set required headers ##################

### verify expected column counts, then overwrite column names so downstream steps
### can reliably reference analytes and metadata (SAMPLE_ID/STD_ID, PROTEIN, VOLUME).

expected_samples_cols <- c("SAMPLE_ID","MHPG", "NE", "DHBA", "DOPAC", "DA", "5-HIAA", "5-HT", "PROTEIN", "VOLUME")
expected_standards_cols <- c("STD_ID", "MHPG", "NE", "DHBA", "DOPAC", "DA", "5-HIAA", "5-HT")

if (ncol(samples) != length(expected_samples_cols)) {
  stop("samples must have ", length(expected_samples_cols), " columns; found ", ncol(samples))
}
if (ncol(standards) != length(expected_standards_cols)) {
  stop("standards must have ", length(expected_standards_cols), " columns; found ", ncol(standards))
}

colnames(samples)   <- expected_samples_cols
colnames(standards) <- expected_standards_cols

###############################################################################

# Compute per-analyte mean across all standards (one mean per analyte column)
std_avg <- standards %>%
  select(-STD_ID) %>%                               # keep only analyte columns
  summarise(across(everything(), ~mean(as.numeric(.x), na.rm = TRUE))) %>%
  pivot_longer(
    cols = everything(),
    names_to = "Analyte",
    values_to = "Avg"
  )

std_avg

###STANDARD CALCULATIONS############################################################################

# LOAD STD_calc directly in R
STD_calc <- data.frame(
  Analyte = c("DOPAC", "DA", "5-HIAA", "5-HT", "NE", "MHPG"),
  `Weight mg` = c(4.44, 10.78, 8.40, 23.50, 15.04, 9.78),
  check.names = FALSE
)

# LOAD ml_wt_ratios directly in R
ml_wt_ratios <- data.frame(
  Analyte = c("DA", "5-HT", "NE", "MHPG", "DHBA"),
  Molecular_weight_ratios = c(0.807735771, 0.746839001, 0.822694209, 0.810486104, 0.632325536),
  Formula = c(
    "C8H11NO2 HCl",
    "C14H19N5O2 H2O4S",
    "C8H11NO3 HCL",
    "(C9H12O4)2 C4H10N2",
    "C7H9NO2 BrH"
  ),
  check.names = FALSE
)

library(dplyr)

# Function: apply molecular-weight correction only to DA / 5-HT / NE

### mw_correct(analyte, value, ratios_df) applies an analyte-specific molecular-weight correction:
### - If analyte is DOPAC, 5-HIAA, or MHPG: it returns the input value unchanged.
### - If analyte is DA, 5-HT, or NE: it looks up the matching Molecular_weight_ratios in ratios_df
###   (after removing any "-" in the analyte name to match labels like "5HT"), and returns value * ratio.
### - If the analyte is not recognised, or no ratio is found for DA/5-HT/NE, it stops with an error

# Updated function: matches analytes robustly (ignores "-" and other punctuation)
mw_correct <- function(analyte, value, ratios_df = ml_wt_ratios) {
  norm <- function(x) toupper(gsub("[^A-Z0-9]", "", x))  # e.g., "5-HIAA" -> "5HIAA", "5-HT" -> "5HT"
  
  a_norm <- norm(analyte)
  
  # Build lookup table with normalised keys
  ratios_lookup <- ratios_df %>%
    transmute(key = norm(Analyte), ratio = Molecular_weight_ratios)
  
  mapply(function(a_key, v) {
    # No correction for these analytes
    if (a_key %in% c("DOPAC", "5HIAA", "MHPG")) return(v)
    
    # Apply MW ratio correction for these analytes
    if (a_key %in% c("DA", "5HT", "NE")) {
      ratio <- ratios_lookup$ratio[match(a_key, ratios_lookup$key)]
      if (length(ratio) == 0 || is.na(ratio)) stop("No molecular weight ratio found for analyte: ", a_key)
      return(v * ratio)
    }
    
    stop("Unknown analyte: ", a_key)
  }, a_norm, value)
}

STD_calc <- STD_calc %>%
  mutate(
    `Step A (mg/ml)` = `Weight mg` / 10,
    `Step B (ng/ml)` = `Step A (mg/ml)` * 20000,
    `Step C (ng/ml)` = `Step B (ng/ml)` * 0.02,
    `Step D (ng/ml)` = `Step C (ng/ml)` / 5,
    `Corrected Step D (ng/ml)` = mw_correct(Analyte, `Step D (ng/ml)`),  # <- Analyte (not Type)
    `Step E (ng/ml)` = `Corrected Step D (ng/ml)` / 6,
    `Step F (ng/ml)` = `Step E (ng/ml)` / 10
  )

# Reorder rows in STD_calc by desired analyte order
desired_order <- c("MHPG", "NE", "DOPAC", "5-HIAA", "DA", "5-HT")

STD_calc <- STD_calc %>%
  mutate(Analyte = factor(Analyte, levels = desired_order)) %>%
  arrange(Analyte) %>%
  mutate(Analyte = as.character(Analyte))  # optional: drop factor after sorting

# Reorder rows in STD_calc by desired analyte order
desired_order <- c("DOPAC", "DA", "5-HIAA", "5-HT", "NE", "MHPG")

STD_calc <- STD_calc %>%
  mutate(Analyte = factor(Analyte, levels = desired_order)) %>%
  arrange(Analyte) %>%
  mutate(Analyte = as.character(Analyte))  # optional: drop factor after sorting

STD_calc

#################################################################################


## ------------------------------------------------------------
## FINAL CONCENTRATION CALCULATION
## ------------------------------------------------------------
library(dplyr)
library(tidyr)
library(readr)

# 0) Choose the standard concentration column from STD_calc based on std_step_used
step_col <- if (toupper(trimws(std_step_used)) == "E") "Step E (ng/ml)" else "Step F (ng/ml)"

# 1) Ensure numeric columns are numeric (clipboard imports often come as character)
num_cols_samples <- c("MHPG","NE","DHBA","DOPAC","DA","5-HIAA","5-HT","PROTEIN","VOLUME")
samples <- samples %>%
  mutate(across(all_of(num_cols_samples), ~ readr::parse_number(as.character(.x))))

standards <- standards %>%
  mutate(across(-STD_ID, ~ readr::parse_number(as.character(.x))))

# 2) Recompute std_avg (mean STD peak area per analyte)
std_avg <- standards %>%
  select(-STD_ID) %>%
  summarise(across(everything(), ~ mean(.x, na.rm = TRUE))) %>%
  pivot_longer(cols = everything(), names_to = "Analyte", values_to = "Avg")

# 3) Compute the shared multiplier K for each sample and store it in samples$K
#    Shared multiplier (simplified from Excel):
#    K = (avg STD area DHBA * sample volume) / (sample DHBA area * sample protein)
std_avg_DHBA <- std_avg %>%
  filter(Analyte == "DHBA") %>%
  pull(Avg)

if (length(std_avg_DHBA) != 1 || is.na(std_avg_DHBA)) {
  stop("Could not obtain a single, non-NA std_avg value for DHBA.")
}

samples <- samples %>%
  mutate(
    K = (std_avg_DHBA * VOLUME) / (DHBA * PROTEIN)
  )

# 4) Build std_ratio: for each analyte, (STD concentration / avg STD area)
#    - STD concentration comes from STD_calc[[step_col]]
#    - STD area comes from std_avg$Avg
analytes_out <- c("MHPG","NE","DOPAC","5-HIAA","DA","5-HT")  # exclude DHBA (internal standard)

std_ratio <- STD_calc %>%
  transmute(
    Analyte = as.character(Analyte),
    STD_conc = as.numeric(.data[[step_col]])
  ) %>%
  inner_join(std_avg, by = "Analyte") %>%
  filter(Analyte %in% analytes_out) %>%
  transmute(
    Analyte,
    value = STD_conc / Avg
  )

# 5) Apply: concentration = K(sample) * sample_area(analyte) * std_ratio(analyte)
#    (Note: your last sentence repeats "area" twice; the intended formula is K * area * std_ratio.)
concentration_long <- samples %>%
  select(SAMPLE_ID, K, all_of(analytes_out)) %>%
  pivot_longer(cols = all_of(analytes_out), names_to = "Analyte", values_to = "area") %>%
  left_join(std_ratio, by = "Analyte") %>%
  mutate(
    concentration = K * area * value
  )

# ---- Wide output (one row per sample, one column per analyte concentration) ----
concentration_wide <- concentration_long %>%
  select(SAMPLE_ID, Analyte, concentration) %>%
  pivot_wider(names_from = Analyte, values_from = concentration)


# ---- Add ratios + round to 3 decimals + final column order ----
concentration_wide <- concentration_wide %>%
  mutate(
    `MHPG/NE`     = ifelse(is.na(MHPG) | is.na(NE) | NE == 0, NA_real_, MHPG / NE),
    `DOPAC/DA`    = ifelse(is.na(DOPAC) | is.na(DA) | DA == 0, NA_real_, DOPAC / DA),
    `5-HIAA/5-HT` = ifelse(is.na(`5-HIAA`) | is.na(`5-HT`) | `5-HT` == 0, NA_real_, `5-HIAA` / `5-HT`)
  ) %>%
  mutate(
    across(
      any_of(c("MHPG","NE","DOPAC","DA","5-HIAA","5-HT","MHPG/NE","DOPAC/DA","5-HIAA/5-HT")),
      ~ round(.x, 3)
    )
  ) %>%
  select(
    SAMPLE_ID,
    `5-HT`, `5-HIAA`, `5-HIAA/5-HT`,
    DA, DOPAC, `DOPAC/DA`,
    NE,
    everything()
  )

concentration_wide

library(openxlsx)

# Filename: "monoamine concentration DD.MM.AA.xlsx"
out_file <- paste0(
  "monoamine concentration ",
  format(Sys.Date(), "%d.%m.%y"),
  ".xlsx"
)

wb <- createWorkbook()
addWorksheet(wb, "concentration_wide")

writeData(wb, sheet = "concentration_wide", x = concentration_wide)

# Format all numeric columns to 3 decimals in Excel
num_cols <- which(vapply(concentration_wide, is.numeric, logical(1)))
if (length(num_cols) > 0) {
  dec3 <- createStyle(numFmt = "0.000")
  addStyle(
    wb, sheet = "concentration_wide", style = dec3,
    rows = 2:(nrow(concentration_wide) + 1),  # +1 header
    cols = num_cols,
    gridExpand = TRUE,
    stack = TRUE
  )
}

setColWidths(wb, "concentration_wide", cols = 1:ncol(concentration_wide), widths = "auto")
freezePane(wb, "concentration_wide", firstRow = TRUE)

saveWorkbook(wb, out_file, overwrite = TRUE)

# Print the full file path
message("Saved Excel file to: ", normalizePath(out_file, winslash = "/", mustWork = FALSE))
