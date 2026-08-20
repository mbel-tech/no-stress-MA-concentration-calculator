"""Tab 2: every editable constant from the R script.

Analyte weights / MW ratios / correction toggles / formulas live in an
EditableTable. The six dilution-chain numbers (A -> F), the E/F selector,
rounding, and which analyte is the internal standard sit below it. Presets
(save/load/export/import/reset) round out the tab.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .. import config as config_mod
from ..config import AnalyteSpec, Config, ConfigError, DilutionChain
from .grid import Column, EditableTable

ANALYTE_COLUMNS = [
    Column("name", "Analyte", width=70, kind="readonly"),
    Column("standard_weight_mg", "Weight (mg)", width=90, kind="float"),
    Column("mw_ratio", "MW ratio", width=100, kind="float"),
    Column("apply_mw_correction", "Correct?", width=70, kind="bool", anchor="center"),
    Column("formula", "Formula", width=170, kind="text"),
    Column("is_internal_standard", "Internal std", width=90, kind="readonly", anchor="center"),
]


class ConstantsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app

        ttk.Label(self, text="Analyte constants", font=("", 10, "bold")).pack(anchor="w")
        self.grid_table = EditableTable(self, ANALYTE_COLUMNS, height=7, on_change=self._on_any_change)
        self.grid_table.pack(fill="x", pady=(2, 10))

        chain = ttk.LabelFrame(self, text="Standard dilution chain (A -> F)", padding=8)
        chain.pack(fill="x", pady=(0, 10))
        self._chain_vars: dict[str, tk.StringVar] = {}
        chain_fields = [
            ("step_a_divisor", "A = Weight / "),
            ("step_b_multiplier", "B = A x "),
            ("step_c_multiplier", "C = B x "),
            ("step_d_divisor", "D = C / "),
            ("step_e_divisor", "E = (corrected D) / "),
            ("step_f_divisor", "F = E / "),
        ]
        for i, (key, label) in enumerate(chain_fields):
            row, col = divmod(i, 3)
            cell = ttk.Frame(chain)
            cell.grid(row=row, column=col, sticky="w", padx=6, pady=3)
            ttk.Label(cell, text=label).pack(side="left")
            var = tk.StringVar()
            entry = ttk.Entry(cell, textvariable=var, width=12)
            entry.pack(side="left")
            var.trace_add("write", lambda *_: self._on_any_change())
            self._chain_vars[key] = var

        other = ttk.LabelFrame(self, text="Other settings", padding=8)
        other.pack(fill="x", pady=(0, 10))

        ttk.Label(other, text="Standard column used:").grid(row=0, column=0, sticky="w", padx=4)
        self.std_step_var = tk.StringVar()
        ttk.Combobox(other, textvariable=self.std_step_var, values=["E", "F"], width=5,
                     state="readonly").grid(row=0, column=1, sticky="w")

        ttk.Label(other, text="Round to (decimals):").grid(row=0, column=2, sticky="w", padx=(20, 4))
        self.round_var = tk.StringVar()
        ttk.Spinbox(other, from_=0, to=8, textvariable=self.round_var, width=5).grid(row=0, column=3, sticky="w")

        ttk.Label(other, text="Internal standard:").grid(row=0, column=4, sticky="w", padx=(20, 4))
        self.internal_var = tk.StringVar()
        self.internal_combo = ttk.Combobox(other, textvariable=self.internal_var, width=10, state="readonly")
        self.internal_combo.grid(row=0, column=5, sticky="w")
        self.internal_combo.bind("<<ComboboxSelected>>", lambda *_: self._on_any_change())

        presets = ttk.LabelFrame(self, text="Presets", padding=8)
        presets.pack(fill="x", pady=(0, 10))
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(presets, textvariable=self.preset_var, width=28, state="readonly")
        self.preset_combo.pack(side="left", padx=(0, 6))
        ttk.Button(presets, text="Load", command=self._load_preset).pack(side="left", padx=2)
        ttk.Button(presets, text="Save as...", command=self._save_preset).pack(side="left", padx=2)
        ttk.Button(presets, text="Export...", command=self._export_preset).pack(side="left", padx=2)
        ttk.Button(presets, text="Import...", command=self._import_preset).pack(side="left", padx=2)
        ttk.Button(presets, text="Reset to defaults", command=self._reset_defaults).pack(side="left", padx=(12, 2))
        self._refresh_preset_list()

        bottom = ttk.Frame(self)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Apply changes", command=self._apply_changes).pack(side="left")
        self.status_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.status_var, foreground="#a00").pack(side="left", padx=10)

        self.load_config(app.config_obj)

    # -- loading a Config into the widgets -----------------------------------

    def load_config(self, cfg: Config) -> None:
        rows = [
            {
                "name": a.name,
                "standard_weight_mg": a.standard_weight_mg,
                "mw_ratio": a.mw_ratio,
                "apply_mw_correction": a.apply_mw_correction,
                "formula": a.formula,
                "is_internal_standard": a.is_internal_standard,
            }
            for a in cfg.analytes
        ]
        self.grid_table.set_rows(rows)

        d = cfg.dilution
        self._chain_vars["step_a_divisor"].set(_fmt(d.step_a_divisor))
        self._chain_vars["step_b_multiplier"].set(_fmt(d.step_b_multiplier))
        self._chain_vars["step_c_multiplier"].set(_fmt(d.step_c_multiplier))
        self._chain_vars["step_d_divisor"].set(_fmt(d.step_d_divisor))
        self._chain_vars["step_e_divisor"].set(_fmt(d.step_e_divisor))
        self._chain_vars["step_f_divisor"].set(_fmt(d.step_f_divisor))

        self.std_step_var.set(cfg.std_step)
        self.round_var.set(str(cfg.round_decimals))

        names = [a.name for a in cfg.analytes]
        self.internal_combo["values"] = names
        self.internal_var.set(cfg.internal_standard)

        self.status_var.set("")

    # -- gathering widgets back into a Config --------------------------------

    def gather_config(self) -> Config:
        """Build, validate, apply and persist a Config from the current
        widget state. Raises ConfigError on invalid input."""
        if self.grid_table.has_errors():
            raise ConfigError("Fix the highlighted analyte cells: " + " ".join(self.grid_table.get_errors()))

        base = self.app.config_obj
        rows = self.grid_table.get_rows()
        chosen_internal = self.internal_var.get()

        analytes = []
        for row in rows:
            analytes.append(AnalyteSpec(
                name=row["name"],
                standard_weight_mg=row["standard_weight_mg"],
                mw_ratio=row["mw_ratio"],
                apply_mw_correction=bool(row["apply_mw_correction"]),
                formula=row["formula"],
                is_internal_standard=(row["name"] == chosen_internal),
            ))

        try:
            dilution = DilutionChain(
                step_a_divisor=_parse_float(self._chain_vars["step_a_divisor"].get()),
                step_b_multiplier=_parse_float(self._chain_vars["step_b_multiplier"].get()),
                step_c_multiplier=_parse_float(self._chain_vars["step_c_multiplier"].get()),
                step_d_divisor=_parse_float(self._chain_vars["step_d_divisor"].get()),
                step_e_divisor=_parse_float(self._chain_vars["step_e_divisor"].get()),
                step_f_divisor=_parse_float(self._chain_vars["step_f_divisor"].get()),
            )
            round_decimals = int(self.round_var.get())
        except ValueError as exc:
            raise ConfigError(f"Dilution chain / rounding fields must be numbers ({exc})") from exc

        cfg = Config(
            analytes=analytes,
            dilution=dilution,
            internal_standard=chosen_internal,
            std_step=self.std_step_var.get(),
            round_decimals=round_decimals,
            ratio_pairs=base.ratio_pairs,
            output_order=base.output_order,
            decimal_separator=base.decimal_separator,
        )
        cfg.validate()
        return cfg

    def _apply_changes(self):
        try:
            cfg = self.gather_config()
        except ConfigError as exc:
            self.status_var.set(str(exc))
            messagebox.showerror("Invalid constants", str(exc))
            return
        config_mod.save_active(cfg)
        self.app.set_config(cfg)
        self.status_var.set("")
        self.app.status_var.set("Constants applied and saved.")

    def _on_any_change(self):
        self.status_var.set("Unsaved changes -- click 'Apply changes' to use them.")

    # -- presets --------------------------------------------------------------

    def _refresh_preset_list(self):
        self.preset_combo["values"] = config_mod.list_presets()

    def _load_preset(self):
        name = self.preset_var.get()
        if not name:
            messagebox.showinfo("No preset selected", "Choose a preset from the dropdown first.")
            return
        try:
            cfg = config_mod.load_preset(name)
        except (ConfigError, OSError) as exc:
            messagebox.showerror("Could not load preset", str(exc))
            return
        config_mod.save_active(cfg)
        self.app.set_config(cfg)
        self.app.status_var.set(f"Loaded preset '{name}'.")

    def _save_preset(self):
        try:
            cfg = self.gather_config()
        except ConfigError as exc:
            messagebox.showerror("Invalid constants", str(exc))
            return
        name = simpledialog.askstring("Save preset", "Preset name (e.g. 'STD batch Mar-2026'):", parent=self)
        if not name:
            return
        try:
            config_mod.save_preset(name, cfg)
        except ConfigError as exc:
            messagebox.showerror("Could not save preset", str(exc))
            return
        self._refresh_preset_list()
        self.preset_var.set(name)
        self.app.status_var.set(f"Saved preset '{name}'.")

    def _export_preset(self):
        try:
            cfg = self.gather_config()
        except ConfigError as exc:
            messagebox.showerror("Invalid constants", str(exc))
            return
        dest = filedialog.asksaveasfilename(
            title="Export constants as...", defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not dest:
            return
        config_mod.export_preset(cfg, __import__("pathlib").Path(dest))
        self.app.status_var.set(f"Exported constants to {dest}")

    def _import_preset(self):
        src = filedialog.askopenfilename(title="Import constants from...", filetypes=[("JSON", "*.json")])
        if not src:
            return
        name = simpledialog.askstring("Import preset", "Save this as preset named:", parent=self)
        if not name:
            return
        try:
            cfg = config_mod.import_preset(__import__("pathlib").Path(src), name)
        except (ConfigError, OSError) as exc:
            messagebox.showerror("Could not import preset", str(exc))
            return
        self._refresh_preset_list()
        self.preset_var.set(name)
        config_mod.save_active(cfg)
        self.app.set_config(cfg)
        self.app.status_var.set(f"Imported preset '{name}' and made it active.")

    def _reset_defaults(self):
        if not messagebox.askyesno(
            "Reset to defaults",
            "This restores every constant to the original R script's values. Continue?",
        ):
            return
        cfg = config_mod.reset_to_defaults()
        self.app.set_config(cfg)
        self.app.status_var.set("Constants reset to defaults.")


def _fmt(value: float) -> str:
    return f"{value:g}"


def _parse_float(text: str) -> float:
    return float(text.strip().replace(",", "."))
