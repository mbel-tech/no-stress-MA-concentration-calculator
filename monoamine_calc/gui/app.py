"""Main application window: three tabs (Data / Constants / Results) sharing
one Config and driving the pure `engine` module."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import config as config_mod
from ..config import Config, ConfigError
from ..engine import EngineError, run
from .constants_tab import ConstantsTab
from .data_tab import DataTab
from .results_tab import ResultsTab


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("no-stress MA concentration calculator")
        self.geometry("1200x760")
        self.minsize(900, 600)

        self.config_obj: Config = config_mod.load_active_or_defaults()
        self.status_var = tk.StringVar(value="Load samples and standards, then click Calculate.")

        notebook = ttk.Notebook(self)
        self.notebook = notebook

        self.data_tab = DataTab(notebook, self)
        self.constants_tab = ConstantsTab(notebook, self)
        self.results_tab = ResultsTab(notebook, self)

        notebook.add(self.data_tab, text="1. Data")
        notebook.add(self.constants_tab, text="2. Constants")
        notebook.add(self.results_tab, text="3. Results")
        notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        status_bar = ttk.Frame(self)
        status_bar.pack(fill="x", side="bottom")
        ttk.Separator(status_bar).pack(fill="x")
        ttk.Label(status_bar, textvariable=self.status_var, padding=(8, 4)).pack(side="left")

    # -- shared state hooks used by the tabs -------------------------------

    def set_config(self, cfg: Config) -> None:
        self.config_obj = cfg
        self.constants_tab.load_config(cfg)
        self.data_tab.sep_var.set(cfg.decimal_separator)

    def on_dataset_loaded(self) -> None:
        self.status_var.set("Data loaded. Review the Constants tab, then click Calculate.")

    def on_dataset_cleared(self) -> None:
        self.status_var.set("Load samples and standards, then click Calculate.")

    def calculate(self) -> None:
        samples_df = self.data_tab.samples_df
        standards_df = self.data_tab.standards_df
        if samples_df is None or standards_df is None:
            messagebox.showwarning(
                "Missing data", "Load both a Samples and a Standards dataset on the Data tab first."
            )
            self.notebook.select(self.data_tab)
            return

        try:
            cfg = self.constants_tab.gather_config()
        except ConfigError as exc:
            messagebox.showerror("Invalid constants", str(exc))
            self.notebook.select(self.constants_tab)
            return
        config_mod.save_active(cfg)
        self.config_obj = cfg

        try:
            result = run(samples_df, standards_df, cfg)
        except EngineError as exc:
            messagebox.showerror("Calculation error", str(exc))
            return

        self.results_tab.show_result(result)
        self.notebook.select(self.results_tab)
        msg = f"Calculated {len(result.concentrations)} sample(s)."
        if result.warnings:
            msg += f" {len(result.warnings)} warning(s) -- see the Results tab."
        self.status_var.set(msg)


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
