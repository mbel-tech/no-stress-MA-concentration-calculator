"""Tab 3: the computed concentration table, warnings, standard-chain
preview, and Excel export."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import excel_out
from ..engine import CalculationResult
from .grid import populate_readonly_tree


class ResultsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app
        self.result: CalculationResult | None = None

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Button(top, text="Calculate", command=self.app.calculate).pack(side="left")
        self.export_btn = ttk.Button(top, text="Export to Excel...", command=self._export, state="disabled")
        self.export_btn.pack(side="left", padx=6)

        self.warnings_frame = ttk.LabelFrame(self, text="Warnings", padding=6)
        self.warnings_text = tk.Text(self.warnings_frame, height=4, fg="#a00", wrap="word")
        self.warnings_text.pack(fill="both", expand=True)
        self.warnings_text.configure(state="disabled")
        # not packed until there is something to show

        ttk.Label(self, text="Concentrations (ng/mg protein)", font=("", 10, "bold")).pack(
            anchor="w", pady=(10, 2)
        )
        result_frame = ttk.Frame(self)
        result_frame.pack(fill="both", expand=True)
        self.result_tree = ttk.Treeview(result_frame, height=10)
        vsb = ttk.Scrollbar(result_frame, orient="vertical", command=self.result_tree.yview)
        hsb = ttk.Scrollbar(result_frame, orient="horizontal", command=self.result_tree.xview)
        self.result_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.result_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        result_frame.grid_columnconfigure(0, weight=1)
        result_frame.grid_rowconfigure(0, weight=1)

        chain_toggle = ttk.Button(self, text="Show / hide standard dilution chain (A -> F)",
                                   command=self._toggle_chain)
        chain_toggle.pack(anchor="w", pady=(10, 2))
        self.chain_frame = ttk.Frame(self)
        self.chain_tree = ttk.Treeview(self.chain_frame, height=7)
        chain_vsb = ttk.Scrollbar(self.chain_frame, orient="vertical", command=self.chain_tree.yview)
        self.chain_tree.configure(yscrollcommand=chain_vsb.set)
        self.chain_tree.grid(row=0, column=0, sticky="nsew")
        chain_vsb.grid(row=0, column=1, sticky="ns")
        self.chain_frame.grid_columnconfigure(0, weight=1)
        self._chain_visible = False

    def show_result(self, result: CalculationResult) -> None:
        self.result = result
        populate_readonly_tree(self.result_tree, result.concentrations)
        populate_readonly_tree(self.chain_tree, result.std_chain, decimals=4)
        self.export_btn.configure(state="normal")

        self.warnings_text.configure(state="normal")
        self.warnings_text.delete("1.0", "end")
        if result.warnings:
            self.warnings_text.insert("1.0", "\n".join(f"⚠ {w}" for w in result.warnings))
            self.warnings_frame.pack(fill="x", before=self.result_tree.master, pady=(0, 8))
        else:
            self.warnings_frame.pack_forget()
        self.warnings_text.configure(state="disabled")

    def _toggle_chain(self):
        self._chain_visible = not self._chain_visible
        if self._chain_visible:
            self.chain_frame.pack(fill="both", expand=False)
        else:
            self.chain_frame.pack_forget()

    def _export(self):
        if self.result is None:
            return
        default_name = excel_out.default_filename()
        dest = filedialog.asksaveasfilename(
            title="Export to Excel", defaultextension=".xlsx",
            initialfile=default_name, filetypes=[("Excel workbook", "*.xlsx")],
        )
        if not dest:
            return
        try:
            out_path = excel_out.write_excel(self.result, self.app.config_obj, Path(dest))
        except OSError as exc:
            messagebox.showerror("Could not save file", str(exc))
            return
        self.app.status_var.set(f"Saved: {out_path}")
        messagebox.showinfo("Saved", f"Saved Excel file to:\n{out_path}")
