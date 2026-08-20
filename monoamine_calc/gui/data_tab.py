"""Tab 1: get samples and standards data into the app.

Each dataset (Samples / Standards) can be loaded three ways, same as the
plan: paste into a box and parse it, read the OS clipboard directly (the
one-click equivalent of the R script's read.delim("clipboard", ...)), or
load a file (.tsv/.csv/.xlsx).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import parsing
from .grid import populate_readonly_tree


class _DatasetPanel(ttk.LabelFrame):
    def __init__(self, parent, app, title: str, loader, columns: list[str]):
        super().__init__(parent, text=title, padding=8)
        self.app = app
        self.loader = loader
        self.columns = columns
        self.df = None

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Read clipboard now", command=self._read_clipboard).pack(side="left")
        ttk.Button(btn_row, text="Parse text below", command=self._parse_box).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Load file...", command=self._load_file).pack(side="left")
        ttk.Button(btn_row, text="Clear", command=self._clear).pack(side="left", padx=4)

        self.text = tk.Text(self, height=5, wrap="none")
        self.text.pack(fill="x", pady=(6, 6))
        self.text.insert(
            "1.0",
            f"Paste tab-separated {title.lower()} data here (with header row: "
            f"{', '.join(columns)}), or use 'Read clipboard now'.",
        )
        self.text.bind("<FocusIn>", self._clear_placeholder_once)
        self._placeholder_cleared = False

        self.status_var = tk.StringVar(value="No data loaded.")
        ttk.Label(self, textvariable=self.status_var, foreground="#555").pack(anchor="w")

        preview_frame = ttk.Frame(self)
        preview_frame.pack(fill="both", expand=True)
        self.preview = ttk.Treeview(preview_frame, height=8)
        vsb = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview.yview)
        hsb = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.preview.xview)
        self.preview.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.preview.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_rowconfigure(0, weight=1)

    def _clear_placeholder_once(self, _event=None):
        if not self._placeholder_cleared:
            self.text.delete("1.0", "end")
            self._placeholder_cleared = True

    def _clear(self):
        self.df = None
        self.text.delete("1.0", "end")
        self._placeholder_cleared = True
        self.preview.delete(*self.preview.get_children())
        self.status_var.set("No data loaded.")
        self.app.on_dataset_cleared()

    def _read_clipboard(self):
        try:
            raw = self.app.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("Clipboard empty", "Could not read the clipboard.")
            return
        self._ingest(raw)

    def _parse_box(self):
        raw = self.text.get("1.0", "end")
        self._ingest(raw)

    def _load_file(self):
        path = filedialog.askopenfilename(
            title=f"Load {self.cget('text')}",
            filetypes=[("Data files", "*.tsv *.csv *.xlsx *.xls"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            raw_df = parsing.read_file(path)
            result = self.loader(raw_df, self.app.config_obj.decimal_separator)
        except parsing.ParsingError as exc:
            messagebox.showerror("Could not load file", str(exc))
            return
        self._apply_result(result)

    def _ingest(self, raw_text: str):
        try:
            raw_df = parsing.read_delimited_text(raw_text)
            result = self.loader(raw_df, self.app.config_obj.decimal_separator)
        except parsing.ParsingError as exc:
            messagebox.showerror("Could not parse data", str(exc))
            return
        self._apply_result(result)

    def _apply_result(self, result: parsing.ParseResult):
        self.df = result.df
        populate_readonly_tree(self.preview, self.df)
        note = ""
        if result.notes:
            note = "  ⚠ " + " ".join(result.notes)
            messagebox.showwarning("Columns matched by position", "\n\n".join(result.notes))
        self.status_var.set(f"Loaded {len(self.df)} row(s), {len(self.df.columns)} columns.{note}")
        self.app.on_dataset_loaded()


class DataTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=10)
        self.app = app

        sep_row = ttk.Frame(self)
        sep_row.pack(fill="x", pady=(0, 8))
        ttk.Label(sep_row, text="Decimal separator used in pasted/loaded numbers:").pack(side="left")
        self.sep_var = tk.StringVar(value=app.config_obj.decimal_separator)
        ttk.Radiobutton(sep_row, text="Dot ( . )  e.g. 1.5", variable=self.sep_var, value=".",
                         command=self._on_sep_change).pack(side="left", padx=(8, 4))
        ttk.Radiobutton(sep_row, text="Comma ( , )  e.g. 1,5", variable=self.sep_var, value=",",
                         command=self._on_sep_change).pack(side="left")

        panels = ttk.Frame(self)
        panels.pack(fill="both", expand=True)
        panels.grid_columnconfigure(0, weight=1)
        panels.grid_columnconfigure(1, weight=1)
        panels.grid_rowconfigure(0, weight=1)

        self.samples_panel = _DatasetPanel(
            panels, app, "Samples", parsing.load_samples, parsing.SAMPLE_COLUMNS
        )
        self.samples_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self.standards_panel = _DatasetPanel(
            panels, app, "Standards", parsing.load_standards, parsing.STANDARD_COLUMNS
        )
        self.standards_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

    def _on_sep_change(self):
        self.app.config_obj.decimal_separator = self.sep_var.get()

    @property
    def samples_df(self):
        return self.samples_panel.df

    @property
    def standards_df(self):
        return self.standards_panel.df
